# LanguageNut API Reference

Base URL: `https://api.languagenut.com`

## Authentication

### POST `loginController/attemptLogin`
Authenticate a user and get a bearer token.

**Params:**
| Param | Type | Description |
|-------|------|-------------|
| `username` | string | The student's username |
| `pass` | string | The student's password (NOT `password`) |

**Response:**
```json
{
  "newToken": "eyJhbGciOiJIUzI1NiIs..."
}
