# User management and authentication

The only sign-in option is Google Sign-In. The client sends its Google ID
credential to the API, which verifies the signature, audience, issuer, and
verified email before issuing a short-lived JWT bearer token for subsequent API
requests. Google login is limited to active users already provisioned by an
administrator; public registration is disabled. Supported access levels are
defined by `AccessLevel` in `services/common/constant/access_level_enum.py`:

- `admin` — manage provisioned users and access the authenticated catalog.
- `reviewer` — access the authenticated catalog; user management is forbidden.

The user-management API accepts only these access levels when creating or
updating a user. Access checks use the user's current database level, so
changes to a user's level take effect immediately without waiting for a token
to expire.

## Configuration

Set `GOOGLE_CLIENT_ID` to the OAuth 2.0 client ID used by the Google Sign-In
client, and set `JWT_SECRET_KEY` to a random secret of at least 32 characters.
Generate the JWT secret locally with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default `30`) and `JWT_ISSUER` (default
`bnhs-platforms`) as needed. Do not commit the JWT secret.

## Initial administrator

Apply migrations first, then set the one-time bootstrap variables and run:

```powershell
$env:BOOTSTRAP_ADMIN_NAME = "Journal Administrator"
$env:BOOTSTRAP_ADMIN_EMAIL = "admin@example.org"
python -m services.user_management.bootstrap_admin
```

Bootstrap refuses to run when any administrator account already exists.
The administrator signs in with Google using the same verified email address.
Bootstrap values are read from the environment, never command-line arguments.

## API

Successful API responses use the common envelope
`{"code": 1, "message": "Success", "data": ...}`. Errors use
`{"code": -1, "message": "Failed", "data": null}`; validation failures also
include an `errors` array with field locations and messages. HTTP status codes
are preserved. The `data` value uses the endpoint's resource-specific schema.

- `POST /api/auth/login` — exchange `{ "credential": "<Google ID token>" }`
  for a bearer token.
- `GET /api/auth/me` — return the authenticated user's profile.
- `GET /api/users` — list users; supports `include_inactive`, `offset`, `limit`.
- `POST /api/users` — provision an account with name, email, and level.
- `GET /api/users/{id}` — retrieve a user.
- `PATCH /api/users/{id}` — update profile fields or active state.
- `DELETE /api/users/{id}` — deactivate an account without deleting history.

All `/api/users` routes require an active administrator bearer token. Login
rejects invalid Google credentials, unverified emails, inactive users, and
Google accounts whose verified email is not provisioned. The first successful
sign-in links the user's immutable Google subject to the account; subsequent
sign-ins use that subject. An administrator cannot deactivate or demote the
last active administrator.

Apply the migration with `alembic upgrade head`.
