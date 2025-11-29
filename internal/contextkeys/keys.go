package contextkeys

// contextKey is an unexported type to prevent collisions with context keys defined in other packages.
type contextKey string

// UserIDKey is the key for the user ID in the context.
const UserIDKey = contextKey("userID")
