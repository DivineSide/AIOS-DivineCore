# Cold Calling Plan — US test prep / tutoring

> **The operational plan for Pang's US cold-calling motion** (the reviews/referrals offer). This doc owns the *operation*: when to call, how to sort the list, which dialer, the number. It does NOT hold the script.
>
> - **Script** → [`cold-call-script.md`](cold-call-script.md)
> - **Offer** → [`../sales-and-delivery/offer.md`](../sales-and-delivery/offer.md)
> - **Warm-reply follow-up** → [`../sales-and-delivery/positive-reply-cadence.md`](../sales-and-delivery/positive-reply-cadence.md)
> - **LinkedIn engage-first sequence** → [`linkedin-playbook.md`](linkedin-playbook.md) §14
>
> Methodology adapted from Pavle's cold-call framework: casual pattern interrupt, no-brainer risk-free offer, book the Zoom to "show" rather than explain, stacked show-up sequence, tonality over script. Voice: casual, plain, no em-dashes, no fabricated claims.
>
> Last updated: 2026-06-15. **Status: dialer not yet locked** (trials and verification in progress, see §5).

---

## 1. The cadence

- **Target: 50 dials/day**, Tuesday / Wednesday / Thursday only. Skip Monday, Friday, and weekends (low connect rates; test-prep owners are teaching or off).
- **Block length: 90 minutes.** 50 manual dials fit in ~75-80 min only if the list is pre-built the night before. A power dialer makes 50 comfortable and frees the wasted dialing/voicemail time.
- **Goal of each call:** start a conversation and book a Zoom, OR collect research. Both count as a win.
- Connect rate on cold B2B is ~10-15%, so expect ~5-8 live conversations per 50 dials.

## 2. The schedule (calling from Malaysia, UTC+8)

Malaysia is **12-15 hours ahead** of the US (US on daylight time through summer). The consequence:

- A Malaysian **morning** block = US **West Coast afternoon**.
- A Malaysian **night** block = US **East/Central morning**.

| US zone | Their prime window (8-10am / 4-5pm local) | = Your time (MYT) |
|---|---|---|
| Eastern (EDT, +12) | 8-10am / 4-5pm | 8-10pm / 4-5am |
| Central (CDT, +13) | 8-10am / 4-5pm | 9-11pm / 5-6am |
| Mountain (MDT, +14) | 8-10am / 4-5pm | 10pm-12am / 6-7am |
| Pacific (PDT, +15) | 8-10am / 4-5pm | 11pm-1am / 7-8am |

**The two blocks:**

| Block | Your time (MYT) | US time | Who you call |
|---|---|---|---|
| **Morning** | 6:30-8:00am | 3:30-5:00pm Pacific | West Coast (CA, WA, OR, NV) |
| **Night** | 9:00-10:30pm | 9-10:30am ET + 8-9:30am CT | East + Central (the bigger market, fits the existing audited pipeline) |

If only one block runs, the **night block is the higher-volume play** (Eastern + Central is the bulk of US businesses, and it matches the already-audited prospects: A+ in PA, DuPage in IL, BWS in OH, Woodlands in TX).

Note: Arizona does not observe DST, so in summer AZ aligns with Pacific time, not Mountain.

## 3. Sort the list by time zone (which block each lead belongs to)

A US number's **area code** (the XXX in +1 XXX-YYY-ZZZZ) maps to a region and therefore a time zone. That is how you split a scraped list into the morning tab vs the night tab.

**The clean way:** Outscraper returns each business address, so **sort by state**, then bucket:

| Time zone | Example states | Block |
|---|---|---|
| Pacific | CA, WA, OR, NV | Morning |
| Mountain | CO, UT, AZ | Morning (AZ behaves as Pacific in summer) |
| Central | TX, IL, MO, MN | Night |
| Eastern | PA, OH, NY, FL, GA | Night |

**Area-code anchors** (to eyeball a number fast):

- **Eastern:** 212/646/917 (NYC), 215 (Philly), 404 (Atlanta), 305 (Miami), 617 (Boston), 614 (Columbus OH), 313 (Detroit)
- **Central:** 312/773 (Chicago), 214/972 (Dallas), 713 (Houston), 512 (Austin), 615 (Nashville), 612 (Minneapolis)
- **Mountain:** 303/720 (Denver), 801 (Salt Lake), 602/480 (Phoenix), 505 (Albuquerque)
- **Pacific:** 415/650/408/510 (Bay Area), 213/310/323/818 (LA), 619/858 (San Diego), 916 (Sacramento), 206 (Seattle), 503 (Portland), 702 (Las Vegas)

**Caveat:** area code = where the number was *registered*, not necessarily where the person is now. For business main lines this is reliable; for owner cell numbers it can be wrong. Trust the **city/state column** if it ever disagrees with the area code.

**Operationally:** in the Outscraper export, add a state (or area-code) column, sort, and split into two tabs: "Pacific/Mountain to morning" and "Central/Eastern to night." Each block, dial straight down the right tab. No thinking mid-session.

## 4. Building the list

Scrape, do not hand-pick (50 dials/day x 3 days = ~150 prospects/week).

- **Tool (in use as of 2026-06-15):** Apify Google Maps scraper, **[CONFIRM exact actor name / URL: it's at the top of the run page, above the search-term box]**. Pay-per-result. Base record returns business name, phone, website, review count + rating, and address; emails + extra phones + socials come from the **Company contacts enrichment** add-on. Supersedes the earlier Outscraper plan (either works; this is the one Pang bought).
- **Run config (this scraper enforces ONE location per run, so build the morning and night lists as separate runs):**
  - *Search term(s)* — add each as its own row: `test prep`, `SAT prep`, `ACT prep`, `tutoring center`, `learning center`.
  - *Location* — set per block, never `USA` (a country-wide run will not sort by coast and dilutes the per-term cap):
    - **Morning / West run:** a Pacific metro, e.g. `Los Angeles, California` (then repeat for Irvine, San Jose, San Diego, Seattle from the metro list below).
    - **Night / East+Central run:** a dense East/Central metro, e.g. `Edison, New Jersey` or `New York, New York` (then Chicago, Dallas, the existing audited metros).
  - *Number of places per search term:* 50 (5 terms ≈ 250 places/run; drop to 20 while still testing cost).
  - *Language:* English.
  - *Add-ons:* **Company contacts enrichment ON** (this is what gets emails). **Reviews / Business leads enrichment / Images OFF** — the review COUNT the hook needs is already in the base record; the Reviews add-on only pulls full review text. Under *Search filters & categories*, set the category to Tutoring / Test preparation if offered and skip permanently-closed places.
- **Target metros, Pacific-first (morning block):** Bay Area / San Jose, LA, Orange County (Irvine), San Diego, Sacramento, Seattle, Portland, Las Vegas, Reno; Mountain: Denver, Salt Lake, Phoenix, Boulder.
- **For the night block:** the existing East/Central pipeline plus East-Coast and Texas/Midwest metros.
- **ICP filter (per [`../identity/icp.md`](../identity/icp.md)):** independent, owner-operated, 2-20 staff, $500k-$3M. **Exclude franchises** (Kumon, Mathnasium, Sylvan, Huntington, C2 Education) and the chains/schools in [`qualify.yaml`](../../../sales_os/Clients/divineside/icps/us-testprep/qualify.yaml). The scraper cannot filter these cleanly, so do it as a post-export step.
- **Sort by the review gap:** established centers with low review counts are the warmest fit for the offer.

## 5. The dialer

**Requirements:** auto power dialer (no manual dialing), a US local number, and ideally local-presence auto-switch.

### Number
- **One US number: 510 (East Bay / Bay Area), ~$5/month.** Rationale: matched to the West Coast morning block. A single number means **no local-presence auto-switch** (that requires a pool of numbers); for one number you simply match the area code to the region you call most. The local-presence boost from one number is modest anyway, and a clean, consistent owned number avoids spam-flagging risk.
- If the motion shifts to the East/Central night block as primary, get an Eastern number instead (e.g. 215 Philly, 212 NYC).

### Tooling decision (NOT yet locked, trials in progress)
- **Leading choice: Kixie Professional (~$65/user/mo).** Has the single-line power dialer (auto-dials) + US number + local presence. It is the tool Pavle uses. Outbound PowerCall (~$95) only adds multi-line/parallel dialing, which is not required. Bills quarterly. Onboarding call booked.
- **Cheaper alternative: CloudTalk Expert (~$50/user/mo)** has the power dialer + local presence, but matches caller ID from numbers you own (not a shared pool), and **restricts virtual caller IDs from Malaysia** (business verification submitted).
- **JustCall Pro** (power dialer + local presence built in, 2-seat minimum ~$98) offered a **manual verification path** (LinkedIn + use explanation in lieu of registration docs).
- **OpenPhone (~$15)** is the cheap manual-dialing fallback to validate the script before committing to a power dialer.
- Other trials in flight: PowerDialer.ai (free plan), Dialpad (Google SSO bypasses domain verification), Myphoner (browser-based, low telecom friction).

### Known friction (the real blocker)
Every telecom dialer runs **business verification (KYC)** before provisioning a US number, and many only send SMS verification codes to US/Canada numbers. Calling from Malaysia with a fresh agency domain (oneboxagency.com) trips both. Workarounds, in order of reliability:
1. **Sign up with Google/Microsoft SSO** (skips email-domain verification).
2. **Manual verification via support** (LinkedIn + intended-use explanation; JustCall and CloudTalk both have this path). This is the most reliable route for a new Malaysia-based sole proprietor.
3. **Own one US number** (e.g. via OpenPhone) so SMS verification codes stop failing on other signups.
4. **Durable fix:** a registered business entity (a Malaysian sole proprietorship via SSM is cheap and fast). Telecom KYC ultimately wants this, and the same wall applies to Twilio, the chosen build-stack provider. Flag to the team.

## 6. Daily run of show

**Night before:**
- Build + sort the next day's list (numbers, names, the one-line hook per prospect, split into morning/night tabs).

**During the block:**
- Open the dialer, dial straight down the correct time-zone tab.
- Keep voicemails to ~15 seconds.
- Log every disposition (the [`/crm` dialer tab](../../../sales_os/web/crm_routes.py) tracks this).
- Book Zooms manually on the call (never send a self-book link).
- Fire the show-up text sequence for every booked call (see [`cold-call-script.md`](cold-call-script.md) §5).

## 7. Open items / blockers

- [ ] **Lock the dialer.** Kixie onboarding call + CloudTalk/JustCall verification pending. Pick whichever clears Malaysia verification first and proves the power dialer + (if possible) local presence work from the user's connection.
- [ ] **Confirm local presence works from Malaysia** on the chosen tool (the unresolved technical question).
- [ ] **Case study divergence (resolve before dialing).** [`cold-call-script.md`](cold-call-script.md) deliberately removed the "doubled another center's reviews in two months" line as a fabricated claim, and the offer currently leans on the two-week free trial as the proof. If the India beachhead client genuinely produced that result, a true case-study line can replace the trial-only framing. If not, do not reintroduce it. Decide which is true before it goes on a live call.

## 8. Cross-references

- Script: [`cold-call-script.md`](cold-call-script.md)
- Offer + guarantee: [`../sales-and-delivery/offer.md`](../sales-and-delivery/offer.md), [`../sales-and-delivery/guarantee.md`](../sales-and-delivery/guarantee.md)
- Warm-reply to booked-call cadence: [`../sales-and-delivery/positive-reply-cadence.md`](../sales-and-delivery/positive-reply-cadence.md)
- Reviews-offer outreach templates (LinkedIn / Loom / email): [`reviews-offer-outreach.md`](reviews-offer-outreach.md)
- ICP filter: [`../identity/icp.md`](../identity/icp.md)
