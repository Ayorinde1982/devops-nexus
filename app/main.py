import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2 import sql
import sentry_sdk

# --- Sentry Initialization (Monitoring) ---
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(title="DevOps URL Shortener")

# --- Database Connection ---
def get_db_connection():
    try:
        # The DATABASE_URL environment variable is used here
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        return conn
    except Exception as e:
        # In a real app, you'd log this error
        print(f"Database connection failed: {e}")
        # Capture the error with Sentry if configured
        if SENTRY_DSN:
            sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=503, detail="Database service unavailable")

# --- Database Setup (Migration) ---
def setup_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # This creates the 'urls' table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                id SERIAL PRIMARY KEY,
                short_code VARCHAR(10) UNIQUE NOT NULL,
                long_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

# Run setup on startup
try:
    setup_db()
except HTTPException:
    # Allow the app to start even if the DB is not immediately available (e.g., in CI)
    print("Warning: Initial database setup failed. This is expected if the DB is not yet running.")
    pass

# --- Pydantic Models ---
class URLCreate(BaseModel):
    long_url: str

class URLResponse(BaseModel):
    short_url: str
    long_url: str

# --- Utility Function ---
import string
import random

def generate_short_code(length=6):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

# --- API Endpoints ---

@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "url-shortener"}

@app.post("/shorten", response_model=URLResponse)
def shorten_url(url_data: URLCreate):
    """Creates a new short URL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    short_code = generate_short_code()
    
    try:
        cursor.execute(
            sql.SQL("INSERT INTO urls (short_code, long_url) VALUES (%s, %s)"),
            (short_code, url_data.long_url)
        )
        conn.commit()
        
        return URLResponse(short_url=f"/{short_code}", long_url=url_data.long_url)
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not shorten URL: {e}")
    finally:
        cursor.close()
        conn.close()

@app.get("/{short_code}")
def redirect_url(short_code: str):
    """Redirects to the long URL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            sql.SQL("SELECT long_url FROM urls WHERE short_code = %s"),
            (short_code,)
        )
        result = cursor.fetchone()
        
        if result is None:
            raise HTTPException(status_code=404, detail="Short URL not found")
            
        long_url = result[0]
        
        # For this demo, we just return the URL
        return {"redirect_to": long_url}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving URL: {e}")
    finally:
        cursor.close()
        conn.close()
