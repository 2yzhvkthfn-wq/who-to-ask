# Fixed values that never come from .env: the allowed values in the fake company data, and the agent's limits.

# HR records
EMPLOYMENT_STATUSES = ["employed", "left"]

# The Teams directory
WORK_LANGUAGES = ["French", "English"]

# Jira tickets
TICKET_TYPES = ["Bug", "Task", "Story", "Access request"]
TICKET_STATUSES = ["Open", "In Progress", "Waiting for Approval", "Reopened", "Resolved", "Closed"]
TICKET_DONE_STATUSES = ["Resolved", "Closed"]
TICKET_PRIORITIES = ["Low", "Medium", "High", "Critical"]

# Confluence pages
PAGE_TYPES = ["doc", "minutes", "agenda"]
PAGE_LANGUAGES = ["en", "fr"]

# MongoDB: how long to wait for the database before giving up, in milliseconds. PyMongo's default is 30 seconds,
# which is a long time to look at a frozen screen when the MongoDB service is simply not running
MONGODB_TIMEOUT_MS = 3000
# The command that copies the files of the data folder into MongoDB. The error messages name it
SEED_COMMAND = "python -m scripts.seed_mongodb"

# Postgres, the memory of the conversations: how long to wait for the database before giving up, in seconds
POSTGRES_TIMEOUT_SECONDS = 3
# How many connections to Postgres the app keeps open at most. The memory uses one at a time,
# and a spare one lets the pool replace a connection that broke
POSTGRES_POOL_SIZE = 2

# The API: the longest question it accepts, in characters. A real question is a sentence or two.
# The limit keeps a program that calls the API from sending a very long text to OpenAI
MAX_QUESTION_LENGTH = 1000

# The page (since M7b) is served from another address than the API: the small server of its build tool, on port 5173.
# A browser only lets a page call an API at another address when the API names that address (this is CORS).
# These are the only addresses the API names
PAGE_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# The agent: an answer recommends at most this many people
MAX_CARDS = 3

# Search: the keyword search and the vector search each return their best 12 tickets and pages.
# Measured on the ten expert questions (M2, and again at M3a): with 12, all their evidence is found.
# verify then reads 12 to 17 texts, and 6 for a "decided" question
SEARCH_TOP_K = 12
# Reciprocal Rank Fusion: an item at rank r in a list gets 1 / (60 + r) points. 60 is the usual value
RRF_K = 60

# verify and write_cards send several small LLM calls together: at most this many run at the same time
LLM_MAX_CONCURRENCY = 8

# The question to the user: when a general word like "the API" fits several systems, the agent asks which one.
# It only asks when the word fits at most this many systems. A word that fits more is too general to ask about
MAX_SYSTEM_CHOICES = 4

# The retry: when nothing holds up in verify, the agent searches again with new words, at most this many times
MAX_RETRIES = 1
# The new words of a retry: at most this many entries
MAX_SEARCH_WORDS = 6

# The grey step lines: a search line repeats the search words only when, written out, they are at most this long
MAX_STEP_WORDS_LENGTH = 80

# Cards: the longest "why" sentence, message middle, and email subject that the LLM may write, in characters.
# A longer text is replaced by a plain one built from the data
MAX_WHY_LENGTH = 250
MAX_MESSAGE_LENGTH = 600
MAX_SUBJECT_LENGTH = 80
# The two optional boxes of the page, "my name" and "my team": the longest text each one accepts, in characters
MAX_USER_TEXT_LENGTH = 60
# The "Send on Teams" button: Microsoft's link that opens a chat with one person, with a message already filled in
# (checked on 2026-11-21 in Microsoft's page "Deep link to a Teams chat")
TEAMS_CHAT_URL = "https://teams.microsoft.com/l/chat/0/0"

# The person lookup: "What does she work on?" lists at most this many tickets and pages, the most recent ones
MAX_WORK_ITEMS = 10
