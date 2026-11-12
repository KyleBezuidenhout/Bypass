"""
Plain-English glossary for every bit of jargon the panel uses.

This is the source of the hover bubbles. It is a backend lookup on purpose:
the UI fetches /glossary once and populates bubbles from it, so wording lives in
one place and can be improved without touching markup.

Definitions are split into:
    short  — one line, shown in the bubble headline area
    long   — a couple of sentences, shown under it
    tip    — an actionable "what this means for you" line
    aliases — other spellings that should resolve to the same entry

Nothing here is invented product behaviour; where a number is a rule of thumb it
says so.
"""

from __future__ import annotations

TERMS: dict[str, dict] = {
    # ---------------------------------------------------------------- concurrency
    "thread": {
        "title": "Thread",
        "short": "One parallel worker.",
        "long": ("GSA opens a fixed number of these at once. Each one is busy loading "
                 "a website and filling in its form. 'max threads = 10' means ten sites "
                 "are being worked on at the same moment."),
        "tip": "More threads = faster, but each one needs its own IP or you get rate-limited.",
        "aliases": ["threads", "worker", "parallel", "concurrency"],
    },
    "usable thread": {
        "title": "Usable thread",
        "short": "A worker that actually has a working proxy behind it.",
        "long": ("This is the whole point of caution with free proxies. If you set 10 threads "
                 "but only 3 of your proxies are alive, you do not get 10x speed — 7 threads "
                 "sit idle waiting for a proxy. A thread is only 'usable' when a live proxy is "
                 "available to it, so the number that matters is not the thread count, it is "
                 "how many threads you can keep fed."),
        "tip": ("That is why the free tier asks for ~8 pool entries per thread: you are "
                "pre-buying spares so dead ones never leave a thread idle."),
        "aliases": ["usable", "live thread", "working thread"],
    },
    # ---------------------------------------------------------------- proxy sourcing
    "residential proxy": {
        "title": "Residential proxy",
        "short": "A proxy running on a real home internet connection.",
        "long": ("The IP belongs to an actual household, so websites see a normal person "
                 "rather than a datacenter. Highest trust, hardest to detect, and the most "
                 "expensive per unit. Usually billed per gigabyte."),
        "tip": "Reserve these for the sites that block everything else.",
        "aliases": ["residential"],
    },
    "static isp proxy": {
        "title": "Static ISP / residential IP",
        "short": "A residential IP that stays the same instead of rotating.",
        "long": ("It is a real home IP, but dedicated to you and not changed on every request. "
                 "Because it is billed per IP, the bandwidth is usually unmetered with no speed "
                 "tier — the closest thing to genuinely 'unlimited'."),
        "tip": "Best fit for form submission: sticky, clean, and unmetered.",
        "aliases": ["static residential", "isp proxy", "static ip"],
    },
    "unlimited residential": {
        "title": "\"Unlimited\" residential",
        "short": "Unmetered bandwidth only — the limit just moves somewhere else.",
        "long": ("No provider sells unlimited bandwidth AND unlimited speed AND unlimited "
                 "threads. 'Unlimited residential' always means the GB counter is removed and "
                 "the cap moves to speed (Mbps), to ports/connections, or to plan length. "
                 "Static ISP IPs are the one product with no GB counter and no speed tier."),
        "tip": "Ask any provider which of the three they cap — if they can't say, don't buy.",
    },
    "rotating": {
        "title": "Rotating proxy",
        "short": "Changes IP on every request, or every few minutes.",
        "long": ("Great for scraping search engines because you look like endless different "
                 "visitors. For form submission a mid-session IP change can look odd, which is "
                 "why sticky sessions exist."),
        "tip": "Use rotating for scraping, sticky for sending.",
        "aliases": ["rotation", "rotating gateway"],
    },
    "sticky session": {
        "title": "Sticky session",
        "short": "Keep the same IP for a while instead of switching every request.",
        "long": ("Some sites set a cookie or session when you land, then expect the same IP back "
                 "when you submit the form. Sticky sessions hold one IP for minutes-to-hours so "
                 "the submit matches the visit."),
        "tip": "Turn sticky on for the sending stage if your provider supports it.",
    },
    "port": {
        "title": "Port (proxy concurrency)",
        "short": "A connection slot on a rotating gateway — the real thread ceiling.",
        "long": ("On port-based plans you are not billed by data, you are billed by how many "
                 "simultaneous connections you may open. Each port can carry roughly one active "
                 "request, so ports map almost directly onto GSA threads."),
        "tip": "Buy ports to match your intended thread count, not your send volume.",
    },
    "layer 1 captcha": {
        "title": "Layer 1 captcha",
        "short": "GSA's own free text recognition.",
        "long": ("Shipped with the app at no cost. It reads simple distorted-text image "
                 "captchas by itself. Anything it cannot read gets handed to a paid service."),
        "tip": "Already on. You never pay for the easy ones.",
        "aliases": ["layer 1"],
    },
    "layer 2 captcha": {
        "title": "Layer 2 captcha",
        "short": "The two independent paid vendors you actually subscribe to.",
        "long": ("Two separate companies, not one, because GSA retries a failed solve on a "
                 "different service. If you only subscribe to one and it goes down, your whole "
                 "run stalls on every captcha-gated form. Two vendors means an outage slows you "
                 "instead of stopping you."),
        "tip": "Buy the primary first, add the backup next. Stop there until a test run proves you need more.",
        "aliases": ["layer 2"],
    },
    "second vendor": {
        "title": "Second vendor",
        "short": "A different company from your primary captcha solver.",
        "long": ("Independence is the point. Two accounts at the same company, or a company and "
                 "its reseller, share infrastructure and therefore share outages. Pick genuinely "
                 "different providers."),
        "tip": "2Captcha + Anti-Captcha is a genuinely independent pair.",
    },
    "captcha services in random order": {
        "title": "Random service order",
        "short": "Rotate your captcha vendors instead of always using the first.",
        "long": ("When enabled, GSA picks a captcha service at random for each solve. Combined "
                 "with configuring a second vendor, one service going down degrades your run "
                 "instead of stopping it."),
        "tip": "Turn this on as soon as you configure more than one captcha service.",
    },
    "use real captcha ip": {
        "title": "Use real captcha ip",
        "short": "Solve captchas from your real IP instead of a proxy.",
        "long": ("Some solving services distrust proxy IPs, or the target site ties the captcha "
                 "to the requesting IP. Sending the captcha job from your own connection can raise "
                 "success rates, at the cost of exposing your home IP to the solver."),
        "tip": "Leave off initially; turn on only if you see captcha rejects.",
    },

    # ---------------------------------------------------------------- ip grade / coverage
    "ip grade": {
        "title": "IP grade",
        "short": "How trustworthy an address looks — the thing that decides whether you get through.",
        "long": ("Sites silently sort incoming traffic by what kind of IP it is. A real home "
                 "connection is trusted. A datacenter (hosting company) address is tolerated. A "
                 "free scraped address is often already flagged. This is invisible to you and "
                 "decides whether your form submit is accepted or quietly binned."),
        "tip": "Grade matters far more than proxy count. Ten good IPs beat a hundred bad ones.",
        "aliases": ["ip grades", "grade", "ip quality", "proxy grade"],
    },
    "coverage": {
        "title": "Coverage",
        "short": "Roughly what share of sites a given IP grade gets through.",
        "long": ("Expressed as a percentage of targets you can reach. There are two different "
                 "numbers and they are not the same: coverage of ordinary harmless sites, and "
                 "coverage of hostile sites that actively block datacenters and known proxy "
                 "ranges. Your real sending success is set by the hostile number."),
        "tip": "Judge a proxy by its hostile-site coverage, not its general one.",
        "aliases": ["reach", "coverage rate", "success rate"],
    },
    "hostile site": {
        "title": "Hostile site",
        "short": "A site that actively tries to block datacenter and proxy traffic.",
        "long": ("Usually sitting behind Cloudflare, a WAF, or anti-bot scoring. It will let an "
                 "innocent-looking visitor through and block a hosting-tier IP. These are the "
                 "sites that decide whether cheap proxies are good enough for you."),
        "tip": "If your niche is full of these, go straight to residential.",
        "aliases": ["hostile", "waf", "cloudflare", "protected site"],
    },
    "professional grade": {
        "title": "Professional / premium grade",
        "short": "The paid tier of IPs — clean address, yours alone, no sharing.",
        "long": ("'Professional grade' is not an official standard, it is shorthand for: dedicated "
                 "(one customer per IP), clean (not previously burned), and unmetered so you can "
                 "run it hard. That is what separates a $0.30 shared IP from a $2.00 dedicated one."),
        "tip": "You do not need premium for scraping; you do want it for sending.",
        "aliases": ["premium", "premium grade", "professional", "premium static", "premium ip"],
    },
    "mobile proxy": {
        "title": "Mobile / 4G proxy",
        "short": "An IP on a phone network — the most trusted kind that exists.",
        "long": ("Because thousands of real phones share one carrier address, sites cannot block "
                 "it without blocking real people, so these get essentially everything. The cost "
                 "is multiples of any other grade."),
        "tip": "Only worth it once residential is still getting blocked somewhere you care about.",
        "aliases": ["mobile", "4g", "mobile ip"],
    },
    "datacenter proxy": {
        "title": "Datacenter proxy",
        "short": "An IP belonging to a hosting company, not a home.",
        "long": ("Fast, cheap and stable, but the address range is publicly known to be a server "
                 "rather than a person. Ordinary sites do not care; hard-to-please ones do."),
        "tip": "Great for scraping and parsing. Risky as your only sending IP on picky targets.",
        "aliases": ["datacenter", "dc proxy", "dc"],
    },

    # ---------------------------------------------------------------- fallback
    "ip fallback": {
        "title": "IP fallback",
        "short": "Retry a failed site with a better IP instead of giving up.",
        "long": ("The idea: if a cheap datacenter IP gets bounced, try the same site through a "
                 "trusted home IP. In GSA this works only partially — proxy settings are stored "
                 "per project, not per site, and the three stage switches are on/off only. So all "
                 "your IPs sit in one shared pool rather than forming an automatic ladder."),
        "tip": "Partial support. Do not expect a true 'try, then upgrade, then upgrade again' flow.",
        "aliases": ["fallback", "fallback system", "ip escalation", "tiered proxies"],
    },
    "retry failed": {
        "title": "Retry failed",
        "short": "Re-attempt sites that failed on the first pass.",
        "long": ("A setting in the project file (currently 0 / off). When on, sites that did not "
                 "get through are attempted again later. Combined with GSA already retrying a dead "
                 "proxy with a different proxy, this is the closest thing the app has to an "
                 "escalation loop."),
        "tip": "Turn it on if you want a second pass at failures. Costs extra requests.",
        "aliases": ["retries", "retry"],
    },
    "deduction": {
        "title": "Deduction (filtering)",
        "short": "Removing hopeless sites before you spend anything on them.",
        "long": ("The cheap half of any smart setup: filter by country, language and url, blacklist "
                 "junk domains, dedupe root domains, skip comment forms. Every site you remove this "
                 "way never consumes an IP request, a thread, or a captcha solve."),
        "tip": "Do this before buying anything. It is pure profit and costs $0.",
        "aliases": ["filtering", "dedupe"],
    },
    "cost per success": {
        "title": "Cost per success",
        "short": "What one actually-delivered submission costs you.",
        "long": ("The only efficiency number that matters. A cheap IP that only reaches 30% of "
                 "hostile sites costs far more per success than a dear IP that reaches 88%. Price "
                 "per IP is meaningless on its own — divide by what it gets through."),
        "tip": "Always compare (price ÷ reach), never price alone.",
        "aliases": ["cost per send"],
    },
    "escalation": {
        "title": "Escalation",
        "short": "Spending more per site only after the cheap attempt fails.",
        "long": ("The appealing half of the idea: pay residential prices only for the sites that "
                 "actually resisted cheaper treatment. It only saves money if the cheap rung "
                 "succeeds often enough that the dear rung sees little traffic."),
        "tip": "Escalation without cutting volume is extra cost, not a saving.",
        "aliases": ["escalate", "upgrade on failure"],
    },

    # ---------------------------------------------------------------- imported list
    "imported list": {
        "title": "Imported list",
        "short": "You supply the websites yourself instead of letting GSA search for them.",
        "long": ("You hand GSA a CSV of targets and it skips the searching entirely, going "
                 "straight to visiting each site and submitting. This removes the single "
                 "strictest, fastest-banning part of the whole job — talking to search engines."),
        "tip": "Massively lowers your proxy requirements and your ban risk.",
        "aliases": ["import", "lead list", "supplied list", "csv import"],
    },
    "export failed": {
        "title": "Export failed",
        "short": "Writes the sites that failed out to a file for you.",
        "long": ("Instead of silently losing failures, GSA dumps them into a file you can look at "
                 "or re-run. With a hand-curated per-person list, a failure is lost work, so this "
                 "is cheap insurance."),
        "tip": "Turn it on and point it at a file. Your curated leads stop vanishing.",
        "aliases": ["failed export"],
    },
    "only root domains": {
        "title": "Only root domains",
        "short": "Contact a company once, not once per subpage.",
        "long": ("Treats example.com and example.com/about as the same lead, so you only reach out "
                 "once. Without it, the same person can receive your message several times."),
        "tip": "Especially important with a personalised list — repeats are obvious.",
        "aliases": ["root domain dedup"],
    },
    "send limit": {
        "title": "Send limit",
        "short": "A cap on how many messages go out per interval.",
        "long": ("Paces your delivery instead of firing everything at once. Keeps sending inside "
                 "business hours and makes a burst of identical-looking submissions less obvious."),
        "tip": "Set one for personalised outreach — it also keeps you looking human.",
    },
    "sticky sessions for sending": {
        "title": "Sticky session (for sending)",
        "short": "Keep the same IP for the whole visit-and-submit, so it matches.",
        "long": ("A site may set a cookie when you first load the form and expect the same IP back "
                 "when you submit. Rotating mid-flow breaks that; a sticky session holds one IP "
                 "long enough for the interaction to look like one person."),
        "tip": "Use sticky for sending, rotating for crawling.",
    },

    # ---------------------------------------------------------------- external tools
    "external parser": {
        "title": "External parser",
        "short": "A third-party service that reads pages instead of GSA doing it.",
        "long": ("GSA finds forms itself using its own field-identification model, so it never calls "
                 "out to a parsing service. That means you cannot simply point it at a better "
                 "parser — you have to route URLs through the other tool and import the results."),
        "tip": "No native hook exists. Any external parser is a pre-step, not a swap.",
        "aliases": ["external parsing", "third party parser"],
    },

    "free allowance": {
        "title": "Free allowance",
        "short": "The amount a service gives you at no cost before it starts charging.",
        "long": ("TinyFish's Fetch free allowance is 1,000 URLs per day and it resets at 00:00 UTC. "
                 "The allowance belongs to the account, which is why a second account genuinely "
                 "gives you a second 1,000 rather than sharing the same one."),
        "tip": "Per account, not per person or per IP — that is what makes farming work.",
        "aliases": ["daily allowance", "free tier", "free quota"],
    },

    "round robin": {
        "title": "Round robin",
        "short": "Spreading work evenly across every option in turn, rather than filling one first.",
        "long": ("With several accounts or proxies, round robin sends request one to option one, "
                 "request two to option two, and so on back to the start. It keeps every account "
                 "under its own limit instead of exhausting one while the rest sit idle."),
        "tip": "The opposite is 'use one until it dies', which is why one key gets throttled.",
        "aliases": ["rotate keys", "key rotation"],
    },

    "account farm": {
        "title": "Account farm",
        "short": "Running several free accounts at once so their limits add up.",
        "long": ("Each TinyFish account gets its own free daily allowance, so N accounts gives "
                 "N times the free capacity. The accounts are separate logins with separate "
                 "emails, but they can all be driven from one script."),
        "tip": "The separation that matters is the email, not the IP — auth is only an API key.",
        "aliases": ["farming", "multi account", "multiple accounts"],
    },

    "stagger": {
        "title": "Stagger",
        "short": "Starting things a moment apart instead of all at the same instant.",
        "long": ("If every account fires its first request in the same millisecond, the traffic "
                 "all arrives from one IP at once and looks heavier than one person. Spacing the "
                 "starts by about a second spreads it out and removes that signal."),
        "tip": "One line of code, and it kills the only real IP-shaped risk in farming.",
        "aliases": ["spacing", "offset the starts", "jitter"],
    },

    "dedicated ip": {
        "title": "Dedicated IP",
        "short": "An IP address only you use, so its reputation is entirely yours.",
        "long": ("Shared IPs inherit the behaviour of everyone else on them. A dedicated IP starts "
                 "clean and stays clean or dirty based on only your sending pattern. For form "
                 "submission this is the difference between a site trusting you and bucketing you "
                 "with a spammer who shares your address."),
        "tip": "The grade you want on the SENDING stage. Shared is fine for parsing.",
        "aliases": ["static isp", "dedicated isp", "static ips"],
    },

    "sticky session": {
        "title": "Sticky session",
        "short": "Staying on the same exit IP for the whole of one job.",
        "long": ("Submitting a form is several requests in a row: load the page, fetch the captcha, "
                 "post the form. If the exit IP changes between those steps the site can lose track "
                 "of you. Sticky means the same IP is held for the whole exchange."),
        "tip": "Rotating proxies are cheap but risky for sending for exactly this reason.",
        "aliases": ["sticky", "session pinning", "pinned session"],
    },

    "sticky session": {
        "title": "Sticky session",
        "short": "Staying on the same exit IP for the whole of one job.",
        "long": ("Submitting a form is several requests in a row: load the page, fetch the captcha, "
                 "post the form. If the exit IP changes between those steps the site can lose track "
                 "of you. Sticky means the same IP is held for the whole exchange."),
        "tip": "Rotating proxies are cheap but risky for sending for exactly this reason.",
        "aliases": ["sticky", "session pinning", "pinned session"],
    },

    # ---------------------------------------------------------------- captcha services
    "captcha service": {
        "title": "Captcha service (a paid solver)",
        "short": "A paid API that solves a captcha for you, billed per solve.",
        "long": ("For a hard captcha GSA can't crack itself, it hands it to one of these. The service "
                 "fetches a token from the captcha endpoint using ITS OWN IPs, then returns the token. "
                 "A per-solve plan is billed per success and its proxy only exists for that one "
                 "request — so you cannot browse a site with it."),
        "tip": "A solver gets you past the puzzle. It does not improve the reputation of YOUR exit IP.",
        "aliases": ["captcha solver", "captcha provider", "solving service"],
    },
    "captcha solve hop": {
        "title": "Captcha solve hop",
        "short": "The one network hop a captcha service covers — and only that one.",
        "long": ("Submitting a form is three hops: you load the page through your proxy, the service "
                 "fetches a token through theirs, then you POST through your proxy. The service only "
                 "ever does the middle hop, so it cannot replace your proxies for the other two."),
        "tip": "This is why captcha subscriptions and proxies are not substitutes — they are separate line items.",
        "aliases": ["solve hop", "captcha hop"],
    },

    # ---------------------------------------------------------------- split testing
    "confound": {
        "title": "Confound",
        "short": "A second difference that could explain your result instead of the thing you tested.",
        "long": ("If arm A and arm B differ in more than one way — different message, different "
                 "captcha settings, different sites — you cannot say the proxies caused the gap. "
                 "A confound is any such extra difference. Hold everything constant except the "
                 "one variable, or balance the rest across arms."),
        "tip": "Clone the project and diff it: the only difference should be the proxy source.",
        "aliases": ["confounding variable", "confounded"],
    },
    "control group": {
        "title": "Control group",
        "short": "A baseline arm you do not change, so you can compare against it.",
        "long": ("In a proxy A/B the control is usually the grade you trust. You send the same kind "
                 "of sites to both arms and compare. An A/A split (same proxies both arms) measures "
                 "pure noise, which sets the smallest difference you can actually believe."),
        "tip": "Always run an A/A arm — it tells you what a 'difference' looks like when nothing changed.",
        "aliases": ["control arm", "aa test", "baseline arm"],
    },

    # ---------------------------------------------------------------- deliverability
    "deliverability": {
        "title": "Deliverability (form outreach)",
        "short": "Of the forms you submit, how many actually land.",
        "long": ("For contact-form outreach deliverability is not email inboxing. It is the share of "
                 "submissions a site actually accepts: the page loads, the captcha passes, and the "
                 "POST is not silently discarded. The two things that move it are your sending "
                 "domain/email reputation and the reputation of the IP you send from."),
        "tip": "It is a percentage you can measure. Send a test batch and track 'Successfully Sent', not replies.",
        "aliases": ["landing rate", "send success rate", "acceptance rate"],
    },

    # ---------------------------------------------------------------- proxy sourcing tails
    "pool entry": {
        "title": "Pool entry",
        "short": "One proxy address sitting in your list.",
        "long": ("A pool entry is a single ip:port with no guarantee it works. GSA tests them "
                 "and discards the dead ones. You need many more entries than the number of "
                 "threads you want to run, because most entries are dead at any given moment."),
        "tip": "Entries are cheap and disposable. Threads are what you actually care about.",
        "aliases": ["pool", "pool entries", "proxy list entry"],
    },
    "live at once": {
        "title": "Live at once",
        "short": "How many entries are working right now.",
        "long": ("Of your whole pool, only a fraction will respond at any instant. "
                 "'Live at once' is that working subset — the only entries that can carry a "
                 "thread. It should be >= your thread count."),
        "tip": "If live-at-once is below your thread count, raise the pool size or use paid proxies.",
    },
    "proxy": {
        "title": "Proxy",
        "short": "A middleman IP address that makes requests on your behalf.",
        "long": ("Instead of all your traffic coming from your home IP, each request goes "
                 "through a different rented/borrowed IP. Search engines see many different "
                 "visitors instead of one greedy one, so they stop rate-limiting you."),
        "tip": "Proxies are what let you raise threads safely. Without them, keep threads low.",
        "aliases": ["proxies"],
    },
    "distinct ips per day": {
        "title": "Distinct IPs per day",
        "short": "How many different proxy IPs you burn through daily.",
        "long": ("Each IP can only take so many requests before a site throttles or bans it. "
                 "The busier you are, the more fresh IPs you must rotate through. Free lists "
                 "refill themselves; paid proxies are limited to the count you buy."),
        "tip": "This is the number to size a paid plan against, not your thread count.",
        "aliases": ["ips per day", "distinct ips"],
    },
    "page requests per site": {
        "title": "Page requests per site",
        "short": "Roughly how many HTTP calls one site costs you.",
        "long": ("Reaching a contact form and submitting it is not one request: find it in "
                 "search results, load the page, fetch the contact page, parse the form, post "
                 "the data. We assume about 8 calls per site. This is a rule of thumb, not a "
                 "measured constant."),
        "tip": "Used only to estimate how many IPs you will burn through.",
    },

    # ---------------------------------------------------------------- stages
    "scraping": {
        "title": "Scraping (finding sites)",
        "short": "The stage that searches the web for candidate sites.",
        "long": ("GSA queries your chosen search engines with your keywords, reads the result "
                 "pages, and collects the URLs it finds. This stage talks mostly to search "
                 "engines, which rate-limit aggressively."),
        "tip": "This stage is the one most likely to get your home IP blocked, so proxies matter here.",
        "aliases": ["scrape", "scraping sites", "searching"],
    },
    "parsing": {
        "title": "Parsing (visiting sites)",
        "short": "The stage that loads each found site and looks for its contact form.",
        "long": ("GSA visits each candidate URL and its likely contact pages, then inspects the "
                 "HTML to find a form it can fill in. Nothing is sent yet."),
        "tip": "Also called 'check sites'. Uses proxies too, but search engines are stricter than normal sites.",
        "aliases": ["parse", "checking sites", "check sites", "visiting"],
    },
    "sending": {
        "title": "Sending (submitting forms)",
        "short": "The stage that actually fills in and submits your message.",
        "long": ("For each site where a form was found, GSA fills the fields, solves any "
                 "captcha, and submits. This is the stage that generates results."),
        "tip": "Clean, stable proxies matter most here — a mid-submit IP change can look suspicious.",
        "aliases": ["send", "submitting", "send sites"],
    },

    # ---------------------------------------------------------------- captcha
    "captcha": {
        "title": "Captcha",
        "short": "The 'prove you are human' puzzle on some contact forms.",
        "long": ("Some sites put a puzzle (image, tickbox, or invisible check) in front of the "
                 "form. GSA cannot solve these itself, so it hands them to a paid solving "
                 "service and pastes the answer back."),
        "tip": "Only a fraction of sites use these. Do a test run first and only pay if you see failures.",
        "aliases": ["captchas", "recaptcha"],
    },
    "captcha solve": {
        "title": "Captcha solve",
        "short": "One captcha handed to a solving service — the unit you are billed per.",
        "long": ("Services charge per solve, typically a fraction of a cent. If your volume is "
                 "1,000 sends/day and 10% of forms are captcha-gated, that is only ~100 solves "
                 "a day, which is cents per month."),
        "tip": "Captcha cost is almost always smaller than you expect. It is not the expensive part.",
        "aliases": ["solve", "solves"],
    },

    # ---------------------------------------------------------------- back to threads
    "ip thread": {
        "title": "IP thread (1 IP = 1 thread)",
        "short": "One proxy per worker, so 40 IPs lets you run 40 workers safely.",
        "long": ("This is the whole difference between cheap and paid proxies. A real, dedicated IP "
                 "does not die mid-run, so each one can carry a worker permanently. Forty IPs means "
                 "forty workers, and you can actually use all of them at once. With free scraped "
                 "proxies you need many spares per worker because most are dead — so 'one IP per "
                 "thread' is a promise only paid proxies can keep."),
        "tip": "Buy 40 IPs → set max threads to 40. Not 400, not 8. Roughly equal.",
        "aliases": ["ip per thread", "one ip per thread", "1:1"],
    },
    "max threads": {
        "title": "Max threads",
        "short": "The dial that sets how many sites GSA works on at the same moment.",
        "long": ("This single number is your speed limit. Set it to the number of live proxies you "
                 "have, and GSA keeps every one of them busy. Set it higher than your proxy count "
                 "and the extra workers sit idle waiting for a free proxy, which feels slower "
                 "without being slower."),
        "tip": "Match it to your IP count. Raising it without more proxies changes nothing.",
        "aliases": ["max thread", "thread count"],
    },
    "sends per day": {
        "title": "Sends per day",
        "short": "How many forms you actually submit in 24 hours.",
        "long": ("The number you plan around. It is roughly your live thread count multiplied by how "
                 "fast each site answers — with 40 threads, expect something in the low thousands "
                 "per day, not tens of thousands."),
        "tip": "This is what you size proxies, captcha and cost against. Start modest, raise it.",
    },
    "idle thread": {
        "title": "Idle thread",
        "short": "A worker with no proxy free to use — paid for, but doing nothing.",
        "long": ("Idle threads are the hidden cost of too few proxies. GSA opened the worker, but "
                 "there was no live IP to hand it, so it sat waiting. Ten threads on three proxies "
                 "means seven of them are decoration."),
        "tip": "If a run feels slow, check live proxy count before raising threads.",
    },

    # ---------------------------------------------------------------- filtering
    "blacklist": {
        "title": "Blacklist",
        "short": "A list of domains you never want to contact.",
        "long": ("Any domain matching the blacklist is skipped entirely before it is visited. "
                 "Useful for excluding directories, your competitors, or sites that never "
                 "respond. Your install ships with a large default blacklist."),
        "tip": "Safe to leave off until you notice recurring junk domains.",
    },
    "dupecheck": {
        "title": "Dupecheck",
        "short": "Stops the same site being contacted twice.",
        "long": ("Before submitting, GSA checks whether this domain was already contacted in an "
                 "earlier run. Very useful across long campaigns; harmful if you deliberately "
                 "want to re-contact someone."),
        "tip": "Leave on for campaigns that run for weeks, off if you are re-approaching a list.",
        "aliases": ["dupe check", "global send dupecheck", "duplicate"],
    },
    "root domain": {
        "title": "Root domain",
        "short": "The bare domain, ignoring the specific sub-page.",
        "long": ("The option to skip root domains avoids contacting `example.com` when you have "
                 "already contacted `example.com/about`. It prevents one company receiving the "
                 "same message through several pages."),
        "tip": "Usually worth enabling — it reduces duplicate outreach sharply.",
    },
    "sublink": {
        "title": "Sublink",
        "short": "A page deeper inside a site, e.g. /contact.",
        "long": ("GSA tries sublinks to find contact pages. If you tell it to skip sublink "
                 "parsing it stays on the page it landed on, which is faster but misses forms "
                 "that live on a separate contact page."),
        "tip": "Leave sublink parsing on unless speed matters more than coverage.",
    },

    # ---------------------------------------------------------------- misc
    "timeout": {
        "title": "Timeout",
        "short": "How long to wait for one site before giving up.",
        "long": ("Measured in seconds. Too low and you mark slow-but-fine sites as failures. "
                 "Too high and a few dead sites hold your threads hostage for a long time."),
        "tip": "120–300 seconds is a sane range. Default is fine.",
        "aliases": ["wait time"],
    },
    "message preview": {
        "title": "Message preview",
        "short": "Preview the outgoing message before it is sent.",
        "long": "Shows you what will actually be submitted, with your macros filled in, so you can spot problems early.",
        "tip": "Handy while setting up; you can turn it off later.",
    },
    "autoscroll": {
        "title": "Autoscroll",
        "short": "Keep the results grid scrolled to the newest row.",
        "long": "Purely cosmetic. It follows progress so you can watch work happen without chasing the scrollbar.",
        "tip": "Purely visual. No effect on speed.",
    },
    "scaling mode": {
        "title": "Scaling mode",
        "short": "How the app stretches on high-DPI screens.",
        "long": ("Controls Windows display scaling behaviour for GSA's own interface. Set it if "
                 "the app looks tiny or blurry on a 4K monitor."),
        "tip": "Values are what the ini stores; the on-screen wording is inferred.",
    },
    "csv macro": {
        "title": "%csv-…% macro",
        "short": "A placeholder that gets replaced by a column from your imported file.",
        "long": ("If your CSV header is `Message`, then writing `%csv-Message%` in the submission "
                 "text makes GSA paste that row's message. This is how you send a unique message "
                 "to every website from one project."),
        "tip": "The macro must match the column header exactly, including capitalisation.",
        "aliases": ["csv always", "%csv%", "macro"],
    },
    "spintax": {
        "title": "Spintax",
        "short": "Random variants inside braces, e.g. {Hi|Hello|Hey}.",
        "long": ("GSA swaps one option at random each time, so the same template reads slightly "
                 "differently to each site. Reduces the 'obviously automated' feel."),
        "tip": "Cheap way to add variety without writing extra templates.",
        "aliases": ["spin"],
    },
    "spinfile": {
        "title": "%spinfile% macro",
        "short": "Pulls a random line from a text file you supply.",
        "long": "Lets you keep a long list of subject lines or openers in a file and have GSA pick one per site.",
        "tip": "Good for large-scale variety; keep the file one option per line.",
    },
    "advanced field": {
        "title": "Advanced field",
        "short": "A setting you rarely need to touch.",
        "long": ("Advanced fields are remembered window sizes, grid column widths and similar. "
                 "'Fill defaults' skips them so clicking it never rearranges your layout."),
        "tip": "Safe to ignore entirely.",
    },
    "proven vs inferred": {
        "title": "proven / inferred",
        "short": "How confident we are the setting is real and correctly described.",
        "long": ("'proven' means the key was found literally in the app's own files and its "
                 "meaning is clear. 'inferred' means the key exists but the human-facing wording "
                 "was deduced, so it is worth double-checking by hand once."),
        "tip": "Anything marked inferred: verify once by toggling it in GSA's own UI.",
        "aliases": ["proven", "inferred"],
    },
    "idempotent": {
        "title": "Idempotent",
        "short": "Safe to run twice — the second run changes nothing.",
        "long": ("Every write in this panel is idempotent and backed up first. Applying the same "
                 "change twice does not double up lines or corrupt the file, and a read-back "
                 "check confirms what actually landed on disk."),
        "tip": "This is why you can click Save repeatedly without fear.",
    },
}


def _index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for key, entry in TERMS.items():
        idx[key.lower()] = key
        for a in entry.get("aliases", []):
            idx[a.lower()] = key
    return idx


INDEX = _index()


def lookup(term: str) -> dict | None:
    key = INDEX.get(term.strip().lower().lstrip("?"))
    if not key:
        return None
    return {"key": key, **TERMS[key]}


def all_terms() -> list[dict]:
    return [{"key": k, **v} for k, v in sorted(TERMS.items())]


def define(*keys: str) -> dict:
    """Convenience for embedding definitions alongside API numbers."""
    out = {}
    for k in keys:
        e = lookup(k)
        if e:
            out[k] = {"short": e["short"], "tip": e.get("tip", "")}
    return out
