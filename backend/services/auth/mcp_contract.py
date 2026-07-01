"""Constants for the pocketid-mcp-as v1.1.0 contract."""

MCP_AS_CONTRACT_NAME = "pocketid-mcp-as"
MCP_AS_CONTRACT_VERSION = "1.1.0"
MCP_TOKEN_PREFIX = "ciqpat_"
MCP_DEFAULT_PATH = "/api/mcp"
MCP_ACCESS_TOKEN_TTL_DAYS = 90
MCP_AS_SCOPES_SUPPORTED = ("openid", "email", "profile")
MCP_AS_CODE_CHALLENGE_METHODS = ("S256",)
MCP_AS_RESPONSE_TYPES = ("code",)
MCP_AS_GRANT_TYPES = ("authorization_code",)
MCP_AS_TOKEN_AUTH_METHODS = ("client_secret_basic", "client_secret_post", "none")
MCP_DCR_REDIRECT_URI_PREFIXES = (
    "https://claude.ai/",
    "https://claude.com/",
    "http://127.0.0.1:",
    "http://127.0.0.1/",
    "http://localhost:",
    "http://localhost/",
    "https://vscode.dev/redirect",
    "https://insiders.vscode.dev/redirect",
)
