app/core/config.py

from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

lru_cache           :   Least Recently Used Cache - put it on function & 
                        it will remember the result of the first call
                        & return that same result for every future call
                        (no need to run the fx again)

BaseSettings        :   Reads values from environment variables automatically
                        (.env). This is a special Pydantic class.

field_validator     :   Decorator that lets you run custom validation logic

SettingsConfigDict  :   A typed configuration object for telling BaseSettings
                        how to behave (which .env file to read, encoding, etc)

pydantic will automatically try to read all the settings from environment variables
(uppercase name). if not found, fall back to default

SYNTAX:

str | None ~ the value can be a string or None

@field_validator("llm_base_url", "docling_base_url")
~   decorator used to register the method below it as a validator for the lister fields.
    pydantic call it automatically after reading those fields.

@classmethod
~   required by Pydantic validators.
    it means the method belongs to the class itself, not to an instance.
    the first argument is cls (the class) instead of self (an instance).

@property
~   turns a method/function into something you access like an attribute,
    not a function call.
    write: settings.llm_url not settings.llm_url()

@lru_cache
~   ensure every subsequent call to get_settings() return the same cache
    Settings object.


app/services/file_service.py

IMPORTS:

logging         :   python's built-in logging module, lets you control log levels
                    (DEBUG INFOR WARNING ERROR) and format output consistently

HTTPException   :   FastAPI class that when raised, will stop the current req & send
                    an HTTP error response to the client (JSON error response)

UploadFile      :   it wraps the raw file data & gives you useful attributes like
                    .filename & methods like .read()

SYNTAX:

__name__    Python's built-in that holds the module's full name. This will tell
            you which file produced each message
        
async def   reading file data from a netowrk req is an I/O operations,
            it takes time waiting for data to arrive. ASync lets FastAPI handle
            other req while waiting.

await       can be used inside an async def. It tells python: "pause here, wait for
            this I/O operation to finish, then continue". While waiting, FastAPI can
            process other incoming request.

file.read() reads all the file bytes into memory


app/services/docling_client.py

IMPORTS:

httpx : modern async-capable HTTP client library for python
        supports async/await.
        recommended for making outbound HTTP request inside async code

SYNTAX:

async with :    the context manager (with) guarantees the connection is closed properly
AsyncClient     even if the request crashes midway


app/services/llm_client.py

this file: 
1. sends the prompt to the LLM
2. does the hevay work of parsing whatever the LLM returns back into a clean Python dict
3. LLM dont always return perfectly formatted JSON, so this file has multiple fallback strategies

IMPORTS:

json    :   encoding & decoding JSON
            json.loads() converts a JSON string into a Python dict
            json.dumps() does the reverse

re      :   regular experessions module
            are the patterns used to search, match / manipulate strings

time    :   module for time-related functions
            used here to measure how long the LLM call takes

SYNTAX:

REGEX

re.sub(pattern, replacement, string)
~   find all matches of pattern in string and replaces them with replacement
    text = re.sub(r',\s*(\])', r'\1', text) ~ for ]
    text = re.sub(r',\s*(\})', r'\1', text) ~ for }


app/features/extraction/router.py

this file:
1. single-file extraction endpoint
2. ties together all the services
3. defines _run_extraction function that the batch router reuses

IMPORTS:

APIRouter   :   FastAPI's way of grouping related endpoints together

File        :   FastAPI marker that tells it to expect a file upload field in 
                the multipart form data.

SYNTAX:

APIRouter(prefix="/extract", tags=["Extraction"])
~   creates a router where every route defined on it automatically get /extract
    prepended to its path
    e.g: @router.post("/from-file") -> /extract/from-file

How the pieces connect
POST /extract/from-file
        │
        ▼
extract_from_file()
        │
        ├─ validate_and_read_upload()   ← file_service.py
        │
        ├─ if PDF: docling_client.pdf_to_text()   ← docling_client.py
        │  else:   decode_txt_bytes()              ← file_service.py
        │
        └─ _run_extraction()
                │
                ├─ build_extraction_prompt()    ← prompt.py
                ├─ llm_client.extract_fields()  ← llm_client.py
                ├─ ExtractionResult(...)        ← schemas.py
                ├─ compare_extraction()         ← reference_service.py
                └─ ExtractResponse(...)         ← schemas.py


app/features/extraction/batch_router.py

IMPORTS:

asyncio             :   for writing async code, provide tools: queue, task & sleep
AsyncGenerator      :   type hint for a function that yields values asynchronously (_stream_batch)
datetime            :   working with dates and times
Path                :   from pathlib module - a modern object oriented way to work with file system paths
FileResponse        :   FastAPI response type that serves a file from disk directly to the client
StreamingResponse   :   FastAPI response type that sends data incrementally as it's generated,
                        instead of waiting for everything to finish first.

SYNTAX:

Path("batch_outputs") ~ creates a Path object pointing to a folder called batch_outputs relative to wherever the app runs.

coro_fn         ~   coroutine function that parameter accepts an async function to call
                    function that takes another function as an argument

*args           ~   captures any positional arguments beyond the named ones into a tuple
                    more than one arguments

**kwargs        ~   captures any keyword arguments into a dict

asyncio.Queue   ~   async safe queue (FIFO) but designed for use in async code
                    one coroutine puts items in, another takes them out
                    it automatically handles the syncronisation between them

AsyncGenerator  ~   return type
                    used yield to produce values asynchronously

function with yield is a generator - it does not run all at once, it runs until the first yield,
pauses and sends that value to the caller, then resumes when the caller asks for the next value.
async make it an async generator that works with await

date_folder.mkdir(parents=True, exist_ok=True)
~   creates the directory
    parents=true: create any missing parent directories
    exist_ok=true: dont raise an error if the directory already exist

