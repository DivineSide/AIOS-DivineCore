# Resource Request — WhatsApp Message to the Owner

> **SENT 2026-06-11** (Mayank, WhatsApp). Modifications from the draft below: language question dropped (answer known: all Hindi, only paper headlines + institute name in English) and engineer-contact question dropped (he'll gladly share when asked).
>
> **ANSWERED 2026-06-11 via voice notes** (summarized in `brain/institute.md`): ~2h per PPT + separate approver; class → PDF export → Telegram/app/WhatsApp distribution; **materials come from his staffer Aryan** — next action is Mayank contacting Aryan for items 1–4. Still open: per-paper time, exact Kruti Dev variant (confirm from Aryan's files).

> Phase-0 ask list (see `brain/spec.md`). Send the Hinglish version on WhatsApp; English version is for team reference. Keep it one message — he's warm and motivated, no persuasion needed, just clarity. No pricing, no AI-architecture talk.

## Hinglish (ready to send)

Namaste sir 🙏

Jaisa baat hui thi, humne aapke content waale system pe kaam shuru kar diya hai. Pehla demo aapki kisi asli class ke material pe hi banaunga, taaki aap khud quality dekh sakein.

Iske liye kuch cheezein chahiye (jis bhi format mein ho — PDF, file, photo, sab chalega):

1. Aapki 3–5 best PPTs — jo aapko sabse achhi lagti hain. Agar koi blank template/format hai toh woh bhi.
2. 3–5 question papers ya quizzes jo aap students ko dete hain.
3. Kisi ek chal rahi batch ka syllabus, aur agle 2 hafte ka class schedule.
4. Jin books/notes se aapki team material banati hai — unke naam ya PDFs.

Aur 4 chhote sawaal:

1. Aapka material Hindi mein hota hai, English mein, ya dono mix?
2. Abhi ek PPT ya ek paper banane mein team ko kitna time lagta hai? Aur final check kaun karta hai?
3. Bani hui PPT students tak kaise pahunchti hai — print, app, ya dono?
4. (Abhi zaroori nahi) Aapke app banane waale engineer ka contact mil sakta hai? Aage kaam aa sakta hai.

Jaise hi yeh mil jayega, main aapki agle kisi class ka poora material bana ke dikhata hoon — aapko apne kaam mein kuch badalna nahi hai, bas yeh bhej dijiye 🙏

## English (team reference)

Namaste sir 🙏

As discussed, we've started work on your content system. I'll build the first demo on a real class's material so you can judge the quality yourself.

For that I need a few things (any format works — PDF, file, photo):

1. 3–5 of your best PPTs — the ones you consider your best. The blank template/format too, if one exists.
2. 3–5 question papers or quizzes you give students.
3. The syllabus of one running batch, plus the class schedule for the next 2 weeks.
4. The books/notes your team builds material from — names or PDFs.

And 4 quick questions:

1. Is your material in Hindi, English, or a mix?
2. How long does one PPT or one paper take the team right now? And who does the final check?
3. How does a finished PPT reach students — print, app, or both?
4. (Not urgent) Could I get your app engineer's contact? May be useful later.

As soon as I have these, I'll generate the complete material for one of your upcoming classes and show you — nothing changes in how you work, just send these over 🙏

## Follow-up message to Aryan (content staffer, friend — casual Hinglish)

> Drafted 2026-06-11 after the owner's voice notes pointed to Aryan as the materials source. Key difference from the owner message: ask for **original files** (.pptx / .doc), not PDFs/photos — we need the real template and Kruti Dev encoding intact.

Oye Aryan bhai 🙌

Mosa ji se baat hui — unke content ka kaam thoda automate kar rahe hain, PPT banane wala. Unhone bola saara material tere paas hai, toh seedha tujhse maang raha hoon 😄

Yeh chahiye, aur **original files bhejna (PPT/Word format mein), PDF ya photo nahi** — kyunki mujhe tumhara exact template aur font waise ka waisa chahiye:

1. 3–5 best PPTs jo tune banayi hain (.pptx file)
2. Agar koi blank template hai jisse shuru karte ho, toh woh bhi
3. 3–5 question papers ya quizzes (Word/original file mein ho toh best)
4. Kisi ek chal rahi batch ka syllabus + agle 2 hafte ka class schedule
5. Jin books/notes se material banate ho — naam bata de ya PDF bhej de

Ek sawaal bhi: typing kis font mein karte ho — Kruti Dev 010 ya koi aur?

Jaise hi yeh milega, ek demo banake dikhata hoon — tera 2 ghante wala PPT kaam minutes mein hone wala hai bhai 😎 Koi confusion ho toh call kar le.

## Why each ask (internal)

| Ask | Feeds |
|---|---|
| Best PPTs + template | Quality bar + `templates/` + format-conventions extraction + Devanagari rendering spike |
| Papers/quizzes | `paper.py` format spec (sections, marks, difficulty, instruction text) |
| Syllabus + schedule | Demo targets a real upcoming class (the "this is real" moment) |
| Source books | Grounding corpus — the anti-hallucination layer |
| Q1 language | Go/no-go language-quality spike |
| Q2 time + QC owner | Baseline for the time-saved math (demo + retainer anchor) |
| Q3 delivery channel | Output format priorities (print-ready vs app upload) |
| Q4 engineer contact | v1.1 app integration (known hidden cost, has lead time) |
