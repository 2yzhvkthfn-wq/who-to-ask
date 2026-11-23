# The fixed texts of the agent's answers, written once in English and once in French.
# The code picks a text by its name and by the language of the question. The LLM never writes them.

# failsafe: the polite refusals. One for a request that is not about work, one for a personal question about a colleague
FAILSAFE_TEXTS = {
    "not_work": {
        "en": (
            "Sorry, I can't help with that. I only answer questions about work: "
            "tell me what you need help with, and I'll look for the right colleague to ask."
        ),
        "fr": (
            "Je regrette, je ne peux pas vous aider pour cela. Je réponds seulement aux questions liées au travail : "
            "dites-moi ce dont vous avez besoin, et je chercherai la bonne personne à qui vous adresser."
        ),
    },
    "personal": {
        "en": "Sorry, I only have work information, so I can't answer personal questions about a colleague.",
        "fr": (
            "Je regrette, je n'ai que des renseignements professionnels : "
            "je ne peux pas répondre aux questions personnelles sur un ou une collègue."
        ),
    },
}

# nobody_found: the honest "nobody" answers. The general one, and the one for a "decided" question when the meeting
# minutes record no decision about it. The last two are for a question about a colleague: nobody has the name that
# was given, or the question gave no name ("her") and the conversation has shown nobody yet
NOBODY_FOUND_TEXTS = {
    "general": {
        "en": (
            "I found nobody to recommend for this question. You can try again with more details: "
            "the name of the system, the project, or what exactly you need."
        ),
        "fr": (
            "Je n'ai trouvé personne à vous recommander pour cette question. Vous pouvez réessayer avec plus de "
            "précisions : le nom du système, le projet, ou ce dont vous avez besoin exactement."
        ),
    },
    "no_decision": {
        "en": (
            "I found no recorded decision about this. You can ask who worked on it instead, "
            'for example: "Who worked on ...?"'
        ),
        "fr": (
            "Je n'ai trouvé aucune décision consignée à ce sujet. Vous pouvez plutôt demander qui y a travaillé, "
            "par exemple : « Qui a travaillé sur ... ? »"
        ),
    },
    "no_person": {
        "en": "I found no one by that name in the directory. Check the spelling, or give me the full name.",
        "fr": (
            "Je n'ai trouvé personne de ce nom dans l'annuaire. Vérifiez l'orthographe, ou donnez-moi le nom complet."
        ),
    },
    "no_one_meant": {
        "en": "I don't know who you mean. Ask again with the person's name.",
        "fr": "Je ne sais pas de qui vous parlez. Reposez votre question avec le nom de la personne.",
    },
    # A request for an expert that names no topic at all ("I need help. Who should I ask?"): nothing is searched,
    # and this text asks what the user needs. What the user types next is a new question, like any other
    "no_topic": {
        "en": (
            "What do you need help with? Tell me the system, the project, or the problem, "
            "and I'll look for the right person."
        ),
        "fr": (
            "Avec quoi avez-vous besoin d'aide ? Dites-moi le système, le projet ou le problème, "
            "et je chercherai la bonne personne."
        ),
    },
    # Several people have the name, and the agent has already asked its one question for this request:
    # it does not ask a second time, and it says what is unclear
    "several_people": {
        "en": "Several people have that name, and I can't tell which one you mean. Ask again with the full name.",
        "fr": (
            "Plusieurs personnes portent ce nom, et je ne sais pas de qui il s'agit. "
            "Reposez votre question avec le nom complet."
        ),
    },
}

# ask_user: the question the agent asks back when it can't choose. The run pauses with it, and the user picks one
# of the choices, which are added in code, from the data. The names of the first two are what the agent asks about
ASK_USER_TEXTS = {
    # A general word of the request ("the API") fits several systems
    "system": {
        "en": "Several systems fit your question. Which one do you mean?",
        "fr": "Plusieurs systèmes correspondent à votre question. Duquel s'agit-il ?",
    },
    # Several people have the name of the request
    "person": {
        "en": "Several people have that name. Which one do you mean?",
        "fr": "Plusieurs personnes portent ce nom. De qui s'agit-il ?",
    },
    # An answer arrived, and no question of the agent is waiting for it (for example, the app was restarted)
    "not_waiting": {
        "en": "I'm no longer waiting for an answer to that question. Please ask your question again.",
        "fr": "Je n'attends plus de réponse à cette question. Veuillez reposer votre question.",
    },
}
# How the system that the user picked is added to the question. The next steps then read the completed question,
# as if the user had typed it. The prompt of understand knows these words ("I mean:", "Je veux dire :")
PICKED_SYSTEM = {"en": "{question} I mean: {name}.", "fr": "{question} Je veux dire : {name}."}

# The person lookup: the sentence that answers a question about a colleague. Every name and number comes from the
# directory. The French sentences never put "de" or "le" before a name, so they are right for every name, and they
# never say "il" or "elle": the directory has no gender field
PERSON_TEXTS = {
    # Someone who left: this sentence is the whole answer. No date, no reason, no contact details
    "left": {
        "en": "{name} no longer works at the company.",
        "fr": "{name} ne travaille plus dans l'entreprise.",
    },
    "manager": {
        "en": "{name}'s manager is {manager}.",
        "fr": "{name} a pour gestionnaire {manager}.",
    },
    "no_manager": {
        "en": "The directory lists no manager for {name}.",
        "fr": "L'annuaire n'indique pas de gestionnaire pour {name}.",
    },
    "manager_left": {
        "en": "{name}'s manager in the directory is {manager}, who no longer works at the company.",
        "fr": "{name} a pour gestionnaire dans l'annuaire {manager}, qui ne travaille plus dans l'entreprise.",
    },
    "work_phone": {
        "en": "{name}'s work phone is {phone}.",
        "fr": "{name} a pour numéro de téléphone au travail le {phone}.",
    },
    "no_work_phone": {
        "en": "The directory has no work phone for {name}.",
        "fr": "L'annuaire n'indique pas de téléphone au travail pour {name}.",
    },
    "work": {
        "en": "Here is what {name} works on, by system.",
        "fr": "Voici sur quoi {name} travaille, par système.",
    },
    # Also the answer for someone who opted out of being found: the two cases read the same, on purpose
    "no_work": {
        "en": "I have no tickets or pages to show for {name}.",
        "fr": "Je n'ai aucun billet ni aucune page à montrer pour {name}.",
    },
    # "Is she away?", "Is he on vacation?", "Is she available?": what the directory says, and nothing more.
    # Never a reason, and never "available": the agent sees no calendar. {date} is a date in words
    "away": {
        "en": "{name} is out of office until {date}.",
        "fr": "{name} est à l'extérieur du bureau jusqu'au {date}.",
    },
    "not_away": {
        "en": "{name} is not marked as out of office.",
        "fr": "L'annuaire n'indique pas d'absence du bureau pour {name}.",
    },
}
# The name of the group, in "what does she work on", for the pages that are about no system
NO_SYSTEM = {"en": "General", "fr": "Général"}
# How one ticket is shown in that list: its id, then its summary. French puts a space before a colon
WORK_TICKET = {"en": "{id}: {title}", "fr": "{id} : {title}"}

# What a person did, in words, for the note about removed people and for a plain "why" sentence.
# {items} is a list of page titles or ticket ids
EVIDENCE_TEXTS = {
    "wrote": {"en": "wrote {items}", "fr": "a rédigé {items}"},
    "decided": {"en": "made the decision recorded in {items}", "fr": "a pris la décision consignée dans {items}"},
    "assigned": {"en": "handled {items}", "fr": "a traité {items}"},
    "approved": {"en": "approved {items}", "fr": "a approuvé {items}"},
}
# The date next to each piece of evidence on a card, and what happened that day. {date} is a date in words.
# "mise à jour" is a noun here ("update of ..."), so the French text is right for a page and for a ticket
EVIDENCE_DATE_TEXTS = {
    "updated": {"en": "updated {date}", "fr": "mise à jour le {date}"},
    "resolved": {"en": "resolved {date}", "fr": "résolu le {date}"},
    "meeting": {"en": "meeting of {date}", "fr": "réunion du {date}"},
}
# The word before the last entry of a list: "A, B and C"
LIST_AND = {"en": "and", "fr": "et"}
# How a page title is quoted in a sentence
TITLE_QUOTES = {"en": '"{title}"', "fr": "« {title} »"}

# The note about the people the HR check removed. Someone who left is named, with what they did.
# Someone who opted out is never named: the note only counts them
NOTE_TEXTS = {
    "left": {
        "en": "{name} {did}, but no longer works at the company.",
        "fr": "{name} {did}, mais ne travaille plus dans l'entreprise.",
    },
    "opted_out_one": {
        "en": "1 person opted out of being found.",
        "fr": "1 personne a choisi de ne pas être trouvée.",
    },
    "opted_out_many": {
        "en": "{count} people opted out of being found.",
        "fr": "{count} personnes ont choisi de ne pas être trouvées.",
    },
    # The agent had already asked its one question, and a general word of the request still fits several systems:
    # it goes on with what it has, and the note says what was unclear
    "unclear_system": {
        "en": "I was not sure which system you mean, so I searched all of them.",
        "fr": "Je ne savais pas de quel système il s'agit, alors j'ai cherché dans tous les systèmes.",
    },
    # The second level of an answer: no ticket and no page is about the exact question, so the cards show the people
    # who work on the system that the question names. The note says so first, so that nobody reads a card as
    # "this person worked on my problem". {systems} is the name of the system, or several names. The two sentences
    # are right for one person and for several
    "same_system": {
        "en": (
            "I found no ticket or page about this exact question. "
            "Here is who works on {systems}: a good place to start."
        ),
        "fr": (
            "Je n'ai trouvé aucun billet ni aucune page sur cette question précise. "
            "Voici qui travaille sur {systems} : c'est un bon point de départ."
        ),
    },
}

# The suggested message of a card. The code writes its first and last sentences, and the LLM writes the middle.
# {user_name} and {user_team} are what the user typed in the two optional boxes of the page
MESSAGE_TEXTS = {
    "opening": {
        "en": "Hi {first_name}, I'm {user_name} from {user_team}.",
        "fr": "Bonjour {first_name}, je suis {user_name}, de l'équipe {user_team}.",
    },
    # What stands in the opening when a box is empty: the user fills it in before sending
    "your_name": {"en": "[your name]", "fr": "[votre nom]"},
    "your_team": {"en": "[your team]", "fr": "[votre équipe]"},
    # When the person is out of office: one more sentence, just before the closing. {date} is a day and a month.
    # The French sentence is right for everyone: the directory has no gender field
    "away": {
        "en": "I see you're away until {date}, so no rush.",
        "fr": "Je vois que vous êtes à l'extérieur du bureau jusqu'au {date}, alors rien ne presse.",
    },
    "closing": {"en": "Thank you!", "fr": "Merci !"},
    # The plain middle, used when the LLM's text can't be used
    "plain_middle": {
        "en": (
            'I have a question about this: "{question}" I saw that you worked on this topic. '
            "Could you help me, or point me to the right person?"
        ),
        "fr": (
            "J'ai une question à ce sujet : « {question} » J'ai vu que vous avez travaillé sur ce sujet. "
            "Pourriez-vous m'aider, ou m'indiquer la bonne personne ?"
        ),
    },
    # The plain middle of the second level: this person works on the system, and nothing says that they worked
    # on the topic of the question
    "plain_middle_system": {
        "en": (
            'I have a question about this: "{question}" I saw that you work on this system. '
            "Could you help me, or point me to the right person?"
        ),
        "fr": (
            "J'ai une question à ce sujet : « {question} » J'ai vu que vous travaillez sur ce système. "
            "Pourriez-vous m'aider, ou m'indiquer la bonne personne ?"
        ),
    },
    # The subject of the email that the "Send by email" button opens. The LLM writes one for each card.
    # When its subject can't be used, the code builds one from the system that the person's evidence is about
    "subject_system": {"en": "{system}: a question", "fr": "{system} : une question"},
    # And when the evidence is about no system (a general page): this one
    "subject": {"en": "A question for you", "fr": "Une question pour vous"},
}

# A date in words, with the day first, as in the titles of the company's own pages: "10 November 2026"
MONTHS = {
    "en": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
    "fr": [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ],
}  # fmt: skip
# French writes the first day of a month "1er": "1er novembre 2026"
FIRST_DAY = {"en": "1", "fr": "1er"}

# The grey step lines: what the agent is doing, one short line per step. English is enough for them.
# The code fills in the counts. A line never names a person
STEP_TEXTS = {
    # understand: how each line starts, then what the request is
    "read": "Read your question: {what}",
    "read_again": "Read your question again, with your answer: {what}",
    "understand_help": "you are looking for someone who can help",
    "understand_did": "you are looking for someone who did the work",
    "understand_decided": "you are looking for the person who decided",
    "understand_no_topic": "it does not say what you need help with",
    "understand_person": "it is about a colleague",
    "understand_unclear": "it could be about {count} systems",
    "understand_not_work": "it is not about work",
    "understand_personal": "it asks for personal information",
    "failsafe": "Declined the question",
    "ask_user": "Noted your answer",
    # search: {words} is empty when a search word is the name of someone in the directory
    "search": "Searched pages and tickets{words}: {results}",
    "search_again": "Searched again{words}: {results}",
    "search_words": " for {words}",
    "verify": "Checked {results}: {kept} really about your question",
    "verify_nothing_new": "No new result to check",
    "rewrite": "Nothing was about your question: picked other search words",
    # same_system: the second level. {systems} is the name of the system that the question names, or several names
    "same_system": "Nothing matched your exact question: took the {items} about {systems} instead",
    "rank": "Found {people} behind these pages and tickets",
    "check_hr": "Removed: {removed}",
    "removed_left": "{people} who left the company",
    "removed_opted_out": "{people} who opted out",
    "removed_nobody": "nobody",
    "write_cards": "Wrote {cards}",
    # nobody_found: one line for each kind of "nobody"
    "nobody_found": "Found nobody to recommend",
    "nobody_found_decision": "Found no recorded decision about this",
    "nobody_found_no_topic": "Searched nothing, and asked what you need",
    "nobody_found_person": "Could not tell which person you mean",
    # find_person: with a name, without one ("her"), and after the user picked someone
    "find_person": "Looked in the directory: {matches}",
    "find_person_shown": "Took the most recent person shown in this conversation",
    "find_person_nobody_shown": "No person was shown yet in this conversation",
    "find_person_picked": "Took the person you picked",
    "person_card": "Prepared the card from the directory",
}
# The nouns that a step line counts: one of them, then several
STEP_NOUNS = {
    "result": ("1 result", "{count} results"),
    "kept": ("1 is", "{count} are"),
    "kept_none": "none is",
    "item": ("1 page or ticket", "{count} pages and tickets"),
    "person": ("1 person", "{count} people"),
    "card": ("the card of 1 person", "the cards of {count} people"),
    "match": ("1 person has that name", "{count} people have that name"),
    "match_none": "nobody has that name",
}

# The labels of a card, for the terminal. French puts a space before a colon
CARD_LABELS = {
    "email": {"en": "Email:", "fr": "Courriel :"},
    "out_of_office": {"en": "Out of office until {date}", "fr": "Absence du bureau jusqu'au {date}"},
    "why": {"en": "Why:", "fr": "Pourquoi :"},
    "evidence": {"en": "Evidence:", "fr": "Références :"},
    "message": {"en": "Suggested message:", "fr": "Message suggéré :"},
    "teams": {"en": "Send on Teams", "fr": "Envoyer sur Teams"},
    "send_email": {"en": "Send by email", "fr": "Envoyer par courriel"},
    # The person card: its own lines, and its two links, which open Teams or the email app with no message
    "manager": {"en": "Manager:", "fr": "Gestionnaire :"},
    "languages": {"en": "Languages:", "fr": "Langues :"},
    "work_phone": {"en": "Work phone:", "fr": "Téléphone au travail :"},
    "open_teams": {"en": "Open a Teams chat", "fr": "Ouvrir une conversation Teams"},
    "write_email": {"en": "Write an email", "fr": "Écrire un courriel"},
}

# The MCP tools (since M8): an AI assistant gets an answer as one short text. These are the lines that the text adds
# around the answer, for the assistant that reads it. English is enough for them, as for the step lines:
# the assistant answers its own user in the user's language
TOOL_TEXTS = {
    # A question of the agent: the line before it, one line per choice, and the line that says how to answer it
    "ask_the_user": "The agent needs one detail before it can answer. Ask the user this question, with its choices:",
    "choice": "- {name} (choice_id: {id})",
    "how_to_pick": (
        "When the user has picked one, call pick_choice with the thread_id below and the choice_id of their pick. "
        "Do not pick for the user. If the user asks something else instead, call ask with the new question."
    ),
    # The last line of every text: the id of the conversation, to send back with a follow-up or with a pick
    "thread": "thread_id: {thread_id}",
}
# The label of the email's subject, under a suggested message. It is in the language of the answer, like the other
# labels of a card. The terminal and the page don't show a subject: there, the "Send by email" link carries it
EMAIL_SUBJECT_LABEL = {"en": "Email subject:", "fr": "Objet du courriel :"}
