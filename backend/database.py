from supabase import create_client, Client
from config import settings


def get_supabase_client() -> Client:
    """Get Supabase client with service role key for backend operations."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_supabase_anon_client() -> Client:
    """Get Supabase client with anon key for public operations."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


# Global client instances
supabase: Client = get_supabase_client()
supabase_anon: Client = get_supabase_anon_client()