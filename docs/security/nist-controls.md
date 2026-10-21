# AtlasOps NIST SP 800-53 Rev 5 Control Mapping

## Scope

This is a **focused subset** of NIST SP 800-53 Rev 5 controls relevant to AtlasOps. It is not a full control catalog (which would exceed 800 controls). Only controls applicable to a self-hosted document processing API are included.

## Access Control (AC)

| Control ID | Control Name | Status | Implementation |
|------------|--------------|--------|----------------|
| AC-2 | Account Management | Implemented | Registration on/off switch (`ALLOW_REGISTRATION`); organizations created per registered user |
| AC-3 | Access Enforcement | Implemented | Organization membership validated on every `/organizations` and `/projects` endpoint via JWT subject |
| AC-6 | Least Privilege | Implemented | Membership roles (`owner`); users only access projects in their own organization |
| AC-17 | Remote Access | Implemented | API access via bearer token over HTTPS; no SSH or direct DB exposure by default |

## Audit and Accountability (AU)

| Control ID | Control Name | Status | Implementation |
|------------|--------------|--------|----------------|
| AU-2 | Audit Events | Partially | Auth events (login/register) and upload/search events logged to stdout; forward via log aggregator |
| AU-6 | Audit Review | Planned | Logs available via container logging driver; no built-in audit UI |
| AU-11 | Audit Record Retention | Planned | Retention policy defined by host log aggregation; not managed by app |

## Identification and Authentication (IA)

| Control ID | Control Name | Status | Implementation |
|------------|--------------|--------|----------------|
| IA-2 | Identification and Authentication (Organizational Users) | Implemented | Email/password authentication with JWT bearer tokens |
| IA-5 | Authenticator Management | Implemented | Argon2id password hashing; 12-character minimum password length |
| IA-5(1) | Authenticator Management / Password Complexity | Implemented | 12+ char minimum enforced at registration |
| IA-7 | Cryptographic Module Authentication | Implemented | JWT signed with `JWT_SECRET` (HS256 via PyJWT) |

## System and Communications Protection (SC)

| Control ID | Control Name | Status | Implementation |
|------------|--------------|--------|----------------|
| SC-7 | Boundary Protection | Implemented | Docker Compose binds all services to localhost-only ports by default; CORS restricted to configured origin |
| SC-8 | Transmission Confidentiality | Implemented | TLS required for production; enforced at reverse proxy/ingress layer |
| SC-28 | Protection of Information at Rest | Partially | Application does not encrypt at rest; relies on host disk/volume encryption |

## System and Information Integrity (SI)

| Control ID | Control Name | Status | Implementation |
|------------|--------------|--------|----------------|
| SI-3 | Malicious Code Protection | Partially | PDF magic-byte validation rejects non-PDF files; no executable content processing |
| SI-4 | Information System Monitoring | Partially | Health endpoint (`/health`); errors logged to stdout; forward via log aggregator |
| SI-7 | Software, Firmware, and Information Integrity | Partially | Pin dependency versions in `requirements.txt` and `package.json` |

## Contingency Planning (CP)

| Control ID | Control Name | Status | Implementation |
|------------|--------------|--------|----------------|
| CP-9 | Information System Backup | Planned | PostgreSQL logical backups + MinIO object storage backups managed by host infrastructure |

## Incident Response (IR)

| Control ID | Control Name | Status | Implementation |
|------------|--------------|--------|----------------|
| IR-4 | Incident Handling | Planned | Documented in `docs/operations/` runbooks; no automated response |
| IR-6 | Incident Reporting | Planned | Logs and status codes available for incident triage |

## Statement of Applicability

Controls marked "Planned" are infrastructure/operational responsibilities of the deploying organization, not implemented within the AtlasOps application code. Controls marked "Partially" are implemented at the application layer but require host-level configuration to be fully effective.
