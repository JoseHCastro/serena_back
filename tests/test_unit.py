"""
Pruebas UNITARIAS para Serena Backend.

A diferencia de los tests de integración (test_auth.py, test_patients.py),
estas pruebas NO usan base de datos real ni el cliente HTTP completo.
Se usan mocks (unittest.mock) para aislar cada componente bajo prueba,
lo que las hace rápidas y ejecutables sin infraestructura externa.

Organización:
    1. Seguridad           — hash_password, verify_password, tokens JWT
    2. Excepciones         — jerarquía de errores de dominio
    3. Esquemas Pydantic   — validaciones de entrada (UserCreate, LoginRequest, etc.)
    4. AuthService         — lógica de negocio con repositorios mockeados
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

# ============================================================================
# SECCIÓN 1 — SEGURIDAD: hashing de contraseñas y tokens JWT
# ============================================================================

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    get_token_subject,
)


class TestPasswordHashing:
    """Pruebas aisladas para las utilidades de hash de contraseñas (bcrypt)."""

    def test_hash_password_produces_bcrypt_hash(self):
        """
        hash_password debe retornar una cadena en formato bcrypt válido.
        Los hashes bcrypt siempre empiezan con '$2b$' seguido del cost factor.
        Esto verifica que estamos usando el algoritmo correcto y no texto plano.
        """
        hashed = hash_password("MiContraseña123")

        # El prefijo '$2b$' identifica bcrypt versión 2b (la más común)
        assert hashed.startswith("$2b$"), (
            "El hash debe ser formato bcrypt ($2b$). "
            "Si falla, hash_password podría estar retornando texto plano."
        )

    def test_verify_password_returns_true_for_correct_password(self):
        """
        verify_password debe retornar True cuando la contraseña en texto plano
        coincide con el hash almacenado.
        Este es el flujo normal del login: el usuario escribe su contraseña,
        nosotros la comparamos contra el hash en la BD.
        """
        plain = "MiContraseña123"
        hashed = hash_password(plain)

        result = verify_password(plain, hashed)

        assert result is True, (
            "verify_password debería retornar True para la contraseña correcta."
        )

    def test_verify_password_returns_false_for_wrong_password(self):
        """
        verify_password debe retornar False cuando la contraseña no coincide.
        Protege contra acceso con credenciales incorrectas.
        Si este test falla, hay una regresión crítica de seguridad.
        """
        hashed = hash_password("ContraseñaCorrecta123")

        result = verify_password("ContraseñaEquivocada456", hashed)

        assert result is False, (
            "verify_password debería retornar False para contraseña incorrecta."
        )

    def test_same_password_generates_different_hashes(self):
        """
        Dos llamadas a hash_password con la misma contraseña deben producir
        hashes DISTINTOS. bcrypt incorpora un salt aleatorio en cada hash.
        Esto previene ataques de rainbow table y diccionario pre-computado.
        """
        password = "MismaContraseña123"

        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2, (
            "bcrypt debe generar hashes únicos con salt aleatorio. "
            "Si son iguales, el salt no está funcionando."
        )
        # Aunque son distintos como cadenas, ambos deben verificar correctamente
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokens:
    """Pruebas para la creación, decodificación y extracción de tokens JWT."""

    def test_access_token_contains_correct_subject(self):
        """
        create_access_token debe codificar el user_id en el campo estándar 'sub'.
        Este campo 'sub' (subject) es lo que luego usamos para identificar al
        usuario en cada request protegido, sin consultar la BD.
        """
        user_id = str(uuid.uuid4())

        token = create_access_token(subject=user_id)
        payload = decode_token(token)

        assert payload["sub"] == user_id, (
            "El campo 'sub' del JWT debe contener el user_id exacto."
        )

    def test_access_token_type_claim_is_access(self):
        """
        El token de acceso debe tener type='access' para diferenciarlo
        del refresh token (type='refresh'). Esto previene usar un refresh token
        como token de acceso o viceversa.
        """
        token = create_access_token(subject="user-abc")
        payload = decode_token(token)

        assert payload["type"] == "access"

    def test_extra_claims_are_included_in_token(self):
        """
        Los extra_claims (rol y email) deben estar presentes en el payload.
        Se incluyen para evitar consultas a la BD en cada request autenticado;
        el middleware lee el rol directamente del token JWT.
        """
        extra = {"role": "therapist", "email": "doc@serena.com"}

        token = create_access_token(subject="user-abc", extra_claims=extra)
        payload = decode_token(token)

        assert payload["role"] == "therapist", "El rol debe estar en el payload del JWT"
        assert payload["email"] == "doc@serena.com", "El email debe estar en el payload"

    def test_get_token_subject_returns_none_for_garbage_token(self):
        """
        get_token_subject debe retornar None (NO lanzar excepción) cuando el
        token es inválido, está corrupto o tiene firma incorrecta.
        El middleware usa esta función para manejar errores de auth con gracia.
        """
        # Un string que no es un JWT válido
        result = get_token_subject("esto.no.es.un.jwt.valido")

        assert result is None, (
            "Token inválido debe retornar None. "
            "Si lanza excepción, el middleware de auth se rompe."
        )

    def test_get_token_subject_returns_user_id_for_valid_token(self):
        """
        Para un token válido, get_token_subject debe extraer el 'sub' correctamente.
        """
        user_id = str(uuid.uuid4())
        token = create_access_token(subject=user_id)

        result = get_token_subject(token)

        assert result == user_id


# ============================================================================
# SECCIÓN 2 — EXCEPCIONES DE DOMINIO
# ============================================================================

from app.core.exceptions import (
    NotFoundError,
    UnauthorizedError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
)


class TestDomainExceptions:
    """
    Pruebas para la jerarquía de excepciones personalizadas.
    Verifican que cada excepción tiene el código HTTP y machine-code correctos,
    lo que garantiza que el exception handler las convierte en la respuesta HTTP adecuada.
    """

    def test_not_found_error_uses_status_404(self):
        """
        NotFoundError debe mapearse a HTTP 404.
        El mensaje debe incluir el nombre del recurso para facilitar el debug.
        """
        exc = NotFoundError("Patient")

        assert exc.status_code == 404
        assert "Patient" in exc.detail  # Ej: "Patient not found."
        assert exc.code == "NOT_FOUND"

    def test_unauthorized_error_uses_status_401(self):
        """
        UnauthorizedError debe mapearse a HTTP 401 (no autenticado).
        Diferente de 403 (autenticado pero sin permisos).
        """
        exc = UnauthorizedError("Token expirado.")

        assert exc.status_code == 401
        assert exc.code == "UNAUTHORIZED"

    def test_unauthorized_error_has_default_message(self):
        """
        UnauthorizedError sin argumentos debe usar el mensaje por defecto.
        Esto evita mensajes vacíos o None cuando se lanza sin contexto.
        """
        exc = UnauthorizedError()

        assert exc.detail == "Could not validate credentials."
        assert len(exc.detail) > 0

    def test_bad_request_error_uses_status_400(self):
        """
        BadRequestError debe mapearse a HTTP 400 (request malformado).
        """
        exc = BadRequestError("El campo 'email' está mal formado.")

        assert exc.status_code == 400
        assert exc.code == "BAD_REQUEST"

    def test_conflict_error_uses_status_409(self):
        """
        ConflictError debe mapearse a HTTP 409.
        Se usa cuando se intenta crear un recurso que ya existe (email duplicado, etc.).
        """
        exc = ConflictError("El email ya está registrado.")

        assert exc.status_code == 409

    def test_forbidden_error_uses_status_403(self):
        """
        ForbiddenError debe mapearse a HTTP 403 (autenticado pero sin permisos).
        Diferente de 401 que indica que ni siquiera está autenticado.
        """
        exc = ForbiddenError()

        assert exc.status_code == 403
        assert exc.code == "FORBIDDEN"

    def test_all_exceptions_are_subclass_of_serena_exception(self):
        """
        Todas las excepciones de dominio deben heredar de SerenaException.
        El exception handler global solo captura SerenaException y sus hijos,
        por lo que romper esta jerarquía haría que los errores no se manejen.
        """
        from app.core.exceptions import SerenaException

        assert issubclass(NotFoundError, SerenaException)
        assert issubclass(UnauthorizedError, SerenaException)
        assert issubclass(BadRequestError, SerenaException)
        assert issubclass(ConflictError, SerenaException)
        assert issubclass(ForbiddenError, SerenaException)


# ============================================================================
# SECCIÓN 3 — ESQUEMAS PYDANTIC: validación de entradas
# ============================================================================

from pydantic import ValidationError
from app.modules.users.schemas import UserCreate
from app.modules.patients.schemas import PatientBase
from app.modules.auth.schemas import LoginRequest


class TestUserCreateSchema:
    """Pruebas para el esquema UserCreate y sus validadores personalizados."""

    def test_valid_payload_passes_validation(self):
        """
        Un payload completo y válido debe construir el modelo sin errores.
        """
        user = UserCreate(
            email="terapeuta@serena.com",
            full_name="Dr. García López",
            role_id=uuid.uuid4(),
            password="SecurePass1",
        )

        assert user.email == "terapeuta@serena.com"

    def test_password_without_digit_raises_validation_error(self):
        """
        El validador 'password_strength' rechaza contraseñas sin ningún dígito.
        Esto refuerza la política de seguridad de contraseñas.

        CÓMO HACER FALLAR ESTE TEST A PROPÓSITO:
            Cambiar la contraseña a "ContieneUnDigito1" — el test fallará
            porque ValidationError NO se lanzará.
        """
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="user@serena.com",
                full_name="Juan Pérez",
                role_id=uuid.uuid4(),
                password="SinNingúnNúmero",  # ← sin dígitos, debe fallar
            )

        # Verificar que el error corresponde al campo 'password'
        errores = exc_info.value.errors()
        campos_con_error = [e["loc"][0] for e in errores]
        assert "password" in campos_con_error

    def test_password_too_short_raises_validation_error(self):
        """
        Contraseñas menores a 8 caracteres deben ser rechazadas por
        el Field(min_length=8) definido en el esquema.
        """
        with pytest.raises(ValidationError):
            UserCreate(
                email="user@serena.com",
                full_name="Juan Pérez",
                role_id=uuid.uuid4(),
                password="Ab1",  # 3 caracteres → demasiado corta
            )

    def test_invalid_email_format_raises_validation_error(self):
        """
        Pydantic usa EmailStr para validar el formato del email.
        Un email malformado debe lanzar ValidationError en el campo 'email'.
        """
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="no-es-email-valido",  # ← sin @ ni dominio
                full_name="Juan Pérez",
                role_id=uuid.uuid4(),
                password="Password123",
            )

        errores = exc_info.value.errors()
        campos_con_error = [e["loc"][0] for e in errores]
        assert "email" in campos_con_error

    def test_full_name_too_short_raises_validation_error(self):
        """
        full_name tiene min_length=2. Un nombre de 1 carácter debe fallar.
        """
        with pytest.raises(ValidationError):
            UserCreate(
                email="user@serena.com",
                full_name="X",  # 1 carácter → muy corto
                role_id=uuid.uuid4(),
                password="Password123",
            )


class TestLoginRequestSchema:
    """Pruebas para el esquema LoginRequest (credenciales de login)."""

    def test_invalid_email_format_is_rejected(self):
        """
        LoginRequest debe rechazar emails con formato inválido.
        Si esto no funciona, usuarios con emails inválidos podrían intentar
        iniciar sesión y generar errores en capas más profundas.
        """
        with pytest.raises(ValidationError):
            LoginRequest(email="no-es-un-email", password="cualquier")

    def test_valid_credentials_pass_schema_validation(self):
        """
        Email válido y contraseña no vacía deben pasar el esquema.
        Nota: la validación del esquema no verifica si las credenciales
        son correctas; eso lo hace AuthService.
        """
        req = LoginRequest(email="admin@serena.com", password="cualquier")

        assert req.email == "admin@serena.com"
        assert req.password == "cualquier"


class TestPatientBaseSchema:
    """Pruebas para la validación de campos del esquema de paciente."""

    def test_empty_first_name_raises_validation_error(self):
        """
        first_name tiene min_length=1; una cadena vacía debe ser rechazada.
        Esto previene registros de pacientes sin nombre en la base de datos.
        """
        with pytest.raises(ValidationError):
            PatientBase(first_name="", last_name="González")

    def test_first_name_exceeding_max_length_is_rejected(self):
        """
        first_name tiene max_length=100; nombres más largos deben fallar.
        """
        nombre_muy_largo = "A" * 101  # 101 caracteres → excede el límite

        with pytest.raises(ValidationError):
            PatientBase(first_name=nombre_muy_largo, last_name="González")

    def test_valid_patient_base_passes(self):
        """
        Nombre y apellido dentro de los límites deben construir el modelo sin errores.
        """
        patient = PatientBase(first_name="María", last_name="González Pérez")

        assert patient.first_name == "María"
        assert patient.last_name == "González Pérez"


# ============================================================================
# SECCIÓN 4 — AUTH SERVICE: lógica de negocio con repositorios mockeados
# ============================================================================

from app.modules.auth.service import AuthService
from app.core.exceptions import UnauthorizedError as UnauthorizedExc


class TestAuthService:
    """
    Pruebas unitarias del AuthService.

    Se mockean los repositorios (UserRepository, RefreshTokenRepository,
    AuditLogRepository) para aislar la lógica de negocio de la base de datos.
    Esto permite testear los casos de negocio sin infraestructura real.
    """

    def _build_service(self):
        """Construye un AuthService con todos los repositorios reemplazados por mocks."""
        db_mock = AsyncMock()
        service = AuthService(db=db_mock)
        # Reemplazar repositorios por mocks async
        service._user_repo = AsyncMock()
        service._token_repo = AsyncMock()
        service._audit_repo = AsyncMock()
        return service

    def _make_active_user(self):
        """Crea un usuario mock activo con contraseña conocida ('Password123!')."""
        user = MagicMock()
        user.id = uuid.uuid4()
        user.email = "doctor@serena.com"
        # Hasheamos la contraseña exactamente como lo haría la BD real
        user.hashed_password = hash_password("Password123!")
        user.is_active = True
        user.role = MagicMock()
        user.role.name = "therapist"
        return user

    @pytest.mark.asyncio
    async def test_login_raises_unauthorized_when_user_not_found(self):
        """
        Si el email no existe en la base de datos (get_by_email retorna None),
        el servicio debe lanzar UnauthorizedError.

        Nunca se revela si el email existe o no (mensaje genérico),
        lo que previene ataques de enumeración de usuarios.
        """
        service = self._build_service()
        # Simular que no existe usuario con ese email
        service._user_repo.get_by_email.return_value = None

        with pytest.raises(UnauthorizedExc):
            await service.login("fantasma@serena.com", "cualquier_pass")

        # Verificar que se intentó buscar al usuario
        service._user_repo.get_by_email.assert_awaited_once_with("fantasma@serena.com")

    @pytest.mark.asyncio
    async def test_login_raises_unauthorized_for_wrong_password(self):
        """
        Si el email existe pero la contraseña no coincide,
        debe lanzarse UnauthorizedError.

        verify_password retornará False al comparar la contraseña incorrecta
        contra el hash bcrypt almacenado.
        """
        service = self._build_service()
        # El usuario existe, pero se enviará una contraseña incorrecta
        service._user_repo.get_by_email.return_value = self._make_active_user()

        with pytest.raises(UnauthorizedExc):
            await service.login("doctor@serena.com", "ContraseñaIncorrecta!")

    @pytest.mark.asyncio
    async def test_login_raises_unauthorized_for_inactive_user(self):
        """
        Un usuario con is_active=False no debe poder iniciar sesión,
        aunque sus credenciales sean correctas.
        Esto permite deshabilitar cuentas sin borrarlas.
        """
        service = self._build_service()
        # Crear usuario inactivo con contraseña correcta
        inactive_user = self._make_active_user()
        inactive_user.is_active = False
        service._user_repo.get_by_email.return_value = inactive_user

        with pytest.raises(UnauthorizedExc):
            # Contraseña correcta pero cuenta desactivada → debe fallar igual
            await service.login("doctor@serena.com", "Password123!")

    @pytest.mark.asyncio
    async def test_login_success_returns_token_response(self):
        """
        Con email existente, contraseña correcta y cuenta activa,
        login debe retornar un TokenResponse con access_token y refresh_token no vacíos.
        """
        service = self._build_service()
        service._user_repo.get_by_email.return_value = self._make_active_user()
        service._user_repo.update_last_login = AsyncMock()
        # token_repo.create retorna un mock de RefreshToken
        service._token_repo.create.return_value = MagicMock()

        result = await service.login("doctor@serena.com", "Password123!")

        # Verificar la estructura del response
        assert result.access_token, "access_token no debe estar vacío"
        assert result.refresh_token, "refresh_token no debe estar vacío"
        assert result.token_type == "bearer"

        # Verificar que se registró el login en el audit log
        service._audit_repo.log.assert_awaited()

    @pytest.mark.asyncio
    async def test_logout_raises_unauthorized_for_revoked_token(self):
        """
        Si el refresh token ya fue revocado o no existe en la BD
        (get_valid_by_raw retorna None), logout debe lanzar UnauthorizedError.

        Esto previene que tokens robados puedan ser usados para logout
        después de ya haber sido invalidados.
        """
        service = self._build_service()
        # Simular token no encontrado o ya revocado
        service._token_repo.get_valid_by_raw.return_value = None

        with pytest.raises(UnauthorizedExc):
            await service.logout("token.invalido.o.ya.revocado")

    @pytest.mark.asyncio
    async def test_logout_revokes_token_when_valid(self):
        """
        Si el refresh token es válido, logout debe invocarse exitosamente
        y el repositorio debe llamar a revoke() sobre ese token.
        """
        service = self._build_service()
        # Simular un token válido encontrado en la BD
        mock_token_record = MagicMock()
        service._token_repo.get_valid_by_raw.return_value = mock_token_record

        await service.logout("token.valido")

        # Verificar que se revocó el token
        service._token_repo.revoke.assert_awaited_once_with(mock_token_record)

    @pytest.mark.asyncio
    async def test_refresh_raises_unauthorized_when_token_not_found(self):
        """
        Si el refresh token no existe en la BD, el refresh debe fallar
        con UnauthorizedError. Protege contra uso de tokens falsos.
        """
        service = self._build_service()
        service._token_repo.get_valid_by_raw.return_value = None

        with pytest.raises(UnauthorizedExc):
            await service.refresh("token.que.no.existe")
