"""
Idempotency Manager

Prevents duplicate appointment bookings on client retries by caching responses
keyed by request ID.
"""

import json
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta


class IdempotencyManager:
    """
    Manages idempotency for appointment booking requests.
    
    Uses in-memory cache (for demo). In production, use Redis with TTL.
    """
    
    def __init__(self, ttl_seconds: int = 86400):  # 24 hours default
        """
        Initialize idempotency manager.
        
        Args:
            ttl_seconds: Time-to-live for cached responses (default 24 hours)
        """
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.enable_logging = True
    
    def get_cached_response(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached response for a request ID.
        
        Args:
            request_id: Unique request identifier
            
        Returns:
            Cached response dict if exists and not expired, None otherwise
        """
        if not request_id:
            return None
        
        cache_key = self._make_cache_key(request_id)
        cached_entry = self.cache.get(cache_key)
        
        if not cached_entry:
            return None
        
        # Check expiration
        created_at = datetime.fromisoformat(cached_entry["created_at"])
        expires_at = created_at + timedelta(seconds=self.ttl_seconds)
        
        if datetime.utcnow() > expires_at:
            # Expired, remove from cache
            del self.cache[cache_key]
            if self.enable_logging:
                print(f"[Idempotency] Expired cache entry for request_id={request_id}")
            return None
        
        if self.enable_logging:
            print(f"[Idempotency] ✅ Cache HIT for request_id={request_id}")
        
        return cached_entry["response"]
    
    def store_response(
        self,
        request_id: str,
        response: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Cache a response for future idempotent requests.
        
        Args:
            request_id: Unique request identifier
            response: Response data to cache
            metadata: Optional metadata about the request
        """
        if not request_id:
            return
        
        cache_key = self._make_cache_key(request_id)
        
        cache_entry = {
            "request_id": request_id,
            "response": response,
            "created_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        self.cache[cache_key] = cache_entry
        
        if self.enable_logging:
            print(f"[Idempotency] 💾 Stored response for request_id={request_id}")
    
    def is_duplicate_request(self, request_id: str) -> bool:
        """
        Check if a request ID has been seen before.
        
        Args:
            request_id: Unique request identifier
            
        Returns:
            True if this is a duplicate request, False otherwise
        """
        return self.get_cached_response(request_id) is not None
    
    def invalidate(self, request_id: str):
        """
        Remove a cached response (for testing or manual invalidation).
        
        Args:
            request_id: Unique request identifier
        """
        cache_key = self._make_cache_key(request_id)
        if cache_key in self.cache:
            del self.cache[cache_key]
            if self.enable_logging:
                print(f"[Idempotency] 🗑️  Invalidated cache for request_id={request_id}")
    
    def clear_all(self):
        """Clear all cached responses (for testing)"""
        self.cache.clear()
        if self.enable_logging:
            print("[Idempotency] 🧹 Cleared all cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        active_count = len(self.cache)
        expired_count = 0
        
        # Count expired entries
        now = datetime.utcnow()
        for entry in self.cache.values():
            created_at = datetime.fromisoformat(entry["created_at"])
            expires_at = created_at + timedelta(seconds=self.ttl_seconds)
            if now > expires_at:
                expired_count += 1
        
        return {
            "total_entries": active_count,
            "expired_entries": expired_count,
            "active_entries": active_count - expired_count,
            "ttl_seconds": self.ttl_seconds
        }
    
    def _make_cache_key(self, request_id: str) -> str:
        """Generate cache key from request ID"""
        # Hash for consistent key format
        return f"idempotency:{hashlib.sha256(request_id.encode()).hexdigest()[:16]}"
    
    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.
        
        Returns:
            Number of entries removed
        """
        now = datetime.utcnow()
        expired_keys = []
        
        for cache_key, entry in self.cache.items():
            created_at = datetime.fromisoformat(entry["created_at"])
            expires_at = created_at + timedelta(seconds=self.ttl_seconds)
            if now > expires_at:
                expired_keys.append(cache_key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys and self.enable_logging:
            print(f"[Idempotency] 🧹 Cleaned up {len(expired_keys)} expired entries")
        
        return len(expired_keys)


# Decorator for automatic idempotency handling

def idempotent(idempotency_manager: IdempotencyManager):
    """
    Decorator to make a function idempotent using request_id.
    
    Usage:
        @idempotent(idempotency_manager)
        def create_appointment(request_id: str, **kwargs):
            # Function body
            return {"appointment_id": "apt-123", "status": "confirmed"}
    """
    def decorator(func):
        def wrapper(request_id: str, *args, **kwargs):
            # Check for cached response
            cached = idempotency_manager.get_cached_response(request_id)
            if cached:
                # Return cached response with idempotency flag
                response = cached.copy()
                response["idempotent"] = True
                return response
            
            # Execute function
            response = func(request_id, *args, **kwargs)
            
            # Cache the response
            idempotency_manager.store_response(request_id, response)
            
            return response
        
        return wrapper
    return decorator


# Request ID validation

def validate_request_id(request_id: Optional[str]) -> bool:
    """
    Validate that request ID meets format requirements.
    
    Args:
        request_id: Request ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not request_id:
        return False
    
    # Must be non-empty string
    if not isinstance(request_id, str) or len(request_id.strip()) == 0:
        return False
    
    # Must be reasonable length (8-128 characters)
    if len(request_id) < 8 or len(request_id) > 128:
        return False
    
    return True


def generate_request_id() -> str:
    """
    Generate a unique request ID.
    
    Returns:
        UUID-based request ID with prefix
    """
    import uuid
    return f"req-{uuid.uuid4()}"
