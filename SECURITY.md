# Security Policy

## Supported version

Security fixes are applied to the latest revision on the `main` branch.

## Reporting a vulnerability

Do not open a public issue containing credentials, OAuth tokens, private email
content, personal information, or an exploitable vulnerability. Contact the
repository owner privately through the hosting platform's security advisory or
private contact mechanism.

Include a concise reproduction, affected revision, and impact. Remove all real
customer and mailbox data from screenshots, logs, databases, and attachments.

## Deployment warning

The bundled Compose credentials and unauthenticated API are intended for a
localhost demonstration environment. Before any network-accessible deployment,
add authentication and authorization, managed secrets, TLS, least-privilege
database credentials, retention controls, monitoring, and backups.

## Secret handling

- Keep `.env`, Gmail OAuth credentials, and Gmail tokens out of Git.
- Never publish extraction databases or JSON generated from a real mailbox.
- Treat message IDs, thread IDs, email bodies, attachments, and agent context as
  potentially sensitive.
- If a secret reaches Git history, revoke or rotate it before rewriting history.
