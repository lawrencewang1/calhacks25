# Security Policy

## Overview

This document outlines the security measures implemented in the CalHacks 2025 Multiplayer AI Chat application and provides guidance for secure deployment and usage.

## Implemented Security Features

### Authentication & Authorization

- **JWT-based Authentication**: Stateless authentication using JSON Web Tokens
- **Password Hashing**: Werkzeug-based secure password hashing (PBKDF2)
- **Strong Password Requirements**:
  - Minimum 12 characters
  - At least one uppercase letter
  - At least one lowercase letter
  - At least one digit
  - At least one special character (!@#$%^&*(),.?":{}|<>_-+=[]\\;/~`)

### Rate Limiting

The application implements rate limiting to prevent abuse:

- **Registration**: 5 attempts per hour per IP address
- **Login**: 10 attempts per minute per IP address
- **Password Change**: 5 attempts per hour per user

### Input Validation

- **Email Validation**: Uses `email-validator` library for RFC-compliant email validation
- **Input Sanitization**: All user inputs are sanitized and length-limited
- **SQL Injection Prevention**: SQLAlchemy ORM prevents SQL injection attacks

### Data Protection

- **Thread Safety**: Thread locks protect shared state from race conditions
- **Database Indexes**: Optimized queries prevent performance-based DoS
- **Secure Session Management**: HTTPOnly and SameSite cookies in production

### Infrastructure Security

- **Environment Variables**: All secrets must be set via environment variables
- **No Hardcoded Secrets**: Development/test environments have safe defaults
- **Logging Framework**: Structured logging with configurable levels
- **CORS Configuration**: Configurable allowed origins

## Security Configuration

### Required Environment Variables

The following environment variables MUST be set in production:

```bash
SECRET_KEY=<your-secret-key>       # Flask session secret
JWT_SECRET_KEY=<your-jwt-secret>   # JWT signing secret
LLM_AUTH_TOKEN=<your-llm-token>    # LLM API authentication
```

Generate secure secrets:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Production Deployment Checklist

- [ ] Set `FLASK_ENV=production`
- [ ] Generate and set strong `SECRET_KEY` and `JWT_SECRET_KEY`
- [ ] Configure `LLM_AUTH_TOKEN` from provider
- [ ] Use PostgreSQL or MySQL (not SQLite)
- [ ] Restrict `CORS_ORIGINS` to specific domains
- [ ] Enable HTTPS (never use HTTP in production)
- [ ] Configure firewall rules
- [ ] Set up log monitoring and alerting
- [ ] Implement backup strategy for database
- [ ] Review and update dependencies regularly

### CORS Configuration

Development:
```bash
CORS_ORIGINS=*
```

Production:
```bash
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

## Known Limitations

### Current Limitations

1. **Rate Limiting Storage**: Uses in-memory storage (resets on restart)
   - **Mitigation**: For production, configure Redis storage

2. **WebSocket Rate Limiting**: WebSocket events not rate-limited
   - **Mitigation**: Implement per-user message throttling

3. **No Account Lockout**: Failed login attempts don't lock accounts
   - **Mitigation**: Monitor logs and implement IP blocking

4. **XSS in Frontend**: Frontend doesn't encode all outputs
   - **Mitigation**: Review and sanitize all dynamic HTML

5. **No CSRF Protection**: CSRF tokens not implemented
   - **Mitigation**: Add CSRF token middleware

### Future Improvements

- [ ] Implement Redis-backed rate limiting for persistence
- [ ] Add WebSocket connection rate limiting
- [ ] Implement account lockout after failed attempts
- [ ] Add comprehensive XSS protection in frontend
- [ ] Implement CSRF token validation
- [ ] Add Content Security Policy (CSP) headers
- [ ] Implement API authentication scoping
- [ ] Add security headers (HSTS, X-Frame-Options, etc.)
- [ ] Implement audit logging for sensitive operations
- [ ] Add 2FA/MFA support

## Vulnerability Reporting

If you discover a security vulnerability, please:

1. **DO NOT** open a public issue
2. Email security concerns to: [security contact]
3. Include detailed description and reproduction steps
4. Allow reasonable time for fix before public disclosure

## Security Best Practices for Developers

### Code Review

- Never commit `.env` files
- Review all user inputs for validation
- Use parameterized queries (ORM)
- Validate all external API responses
- Sanitize data before logging

### Testing

- Test authentication flows thoroughly
- Verify rate limiting works correctly
- Test with malicious inputs
- Validate proper error handling
- Check for information leakage in errors

### Dependencies

- Regularly update dependencies
- Monitor security advisories
- Use `pip-audit` or similar tools
- Pin dependency versions in production

## Incident Response

In case of a security incident:

1. **Assess**: Determine scope and impact
2. **Contain**: Disable affected systems if necessary
3. **Investigate**: Review logs and trace attack vector
4. **Remediate**: Fix vulnerability and restore services
5. **Document**: Record findings and preventive measures
6. **Notify**: Inform affected users if data was compromised

## Compliance Notes

This application handles:
- User authentication credentials (hashed)
- Chat messages (may contain PII)
- User email addresses

Ensure compliance with:
- GDPR (if serving EU users)
- CCPA (if serving California users)
- Other applicable data protection regulations

## Security Updates

This document is updated regularly. Last updated: October 26, 2025

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/latest/security/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
