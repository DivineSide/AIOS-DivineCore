# -*- coding: utf-8 -*-
"""syllabus — the OFFICIAL UKSSSC topic taxonomy, per corpus subject.

WHY THIS EXISTS (exam mode only): subject mode infers topics from a random
PYQ sample, which is correct when no exam context exists — but it is
backward-looking (PYQs lag syllabus revisions by years) and its variety is
capped by whatever the sample happens to contain. Exam mode has a real
anchor: the commission's own published syllabus. Topics here seed
generation FIRST; PYQs then serve their other role (style examples per
topic, via pyq_rag_lookup) — and when a syllabus topic has no PYQ coverage
yet, generation proceeds anyway (style prompt degrades gracefully), which
is exactly how a NEW syllabus topic gets covered before any past paper
tests it.

CANONICAL SOURCE (rewritten 2026-09-10 — read page-by-page from the PDF):

  corpus/syllabus-official/syllabus-2026-08-31-snatak-level-OFFICIAL.pdf
  "उत्तराखण्ड अधीनस्थ कार्यालय स्नातक स्तरीय (समूह 'ग') सेवा परीक्षा की
  परीक्षा योजना / पाठ्यक्रम" — published by UKSSSC 31-Aug-2026, approving
  the Commission's proposal letter 33/गोपन/2026-27 dated 17-Aug-2026.
  Signed by परीक्षा नियंत्रक + सचिव (UKSSSC) and अनुभाग अधिकारी (Uttarakhand
  Shasan). 10 pages; the syllabus proper is "Page 1 of 7"–"Page 7 of 7",
  given BILINGUALLY (each section in Hindi, then English).

  Exam scheme (unchanged from prior years): ONE objective paper,
  100 questions / 100 marks / 2 hours, plus a qualifying typing test.
      01  सामान्य हिंदी                          20 अंक
      02  सामान्य ज्ञान एवं सामान्य अध्ययन        40 अंक
          2.1 सामान्य बुद्धि परीक्षण एवं तर्कशक्ति
          2.2 इतिहास   2.3 भूगोल   2.4 राजनीति विज्ञान
          2.5 अर्थशास्त्र   2.6 समसामयिक घटनाएँ
          2.7 कंप्यूटर का आधारभूत ज्ञान
      2.8 उत्तराखण्ड का सामान्य ज्ञान             40 अंक

  SUPERSEDES विज्ञापन 70/2025 (09-Apr-2025) and विज्ञापन 65/2024, both still
  archived in corpus/syllabus-official/. UKSSSC continues to reuse ONE master
  syllabus across its general written exams; genuinely different syllabi exist
  only for specialist posts (Livestock Extension Officer, Driver — PDFs
  archived, neither wired here).

THIS FILE IS A TRANSCRIPTION, NOT A DECOMPOSITION (changed 2026-09-10).
The previous version hand-split the official compound bullets into ~156
"question-sized" topics. That was well-intentioned but (a) made the file an
interpretation that could not be checked against the source, and (b) did not
actually fix granularity — uk-culture still had only 9 topics for 12 questions
per paper, so ~4 of 6 sampled topics repeated between any two papers.
Question-sized granularity is now the job of the SUBTOPIC layer (mined from
book_passages, see rag/RAG_ROADMAP.md), not of this file. Here we stay faithful
to the commission's own wording so "canonical" means canonical.

MAPPING to corpus subjects (book_passages convention, verified in DB):
  01 सामान्य हिंदी   -> hindi
  2.1 तर्कशक्ति      -> reasoning      NEW 2026-09-10. No corpus, no
                                      SUBJECT_MIX entry, so nothing allocates
                                      to it yet — present so the taxonomy is
                                      complete and so the figure generator has
                                      the commission's own list to build from.
                                      Verbal items need neither figures NOR
                                      RAG; non-verbal items are the
                                      code-generated-figure workstream.
  2.2-2.6            -> general-gk
  2.7 कंप्यूटर        -> computer
  2.8 उत्तराखण्ड      -> uk-history / uk-geography / uk-culture /
                        uk-general-studies (the official 8 bullets split by
                        corpus subject — the ONLY place this file still
                        reorganises the source, because the corpus is
                        partitioned that way)

DIFFS the 2026 syllabus introduced vs the old 70/2025-derived file:
  * तर्कशक्ति is now ENUMERATED (27 named topics). Previously absent entirely.
  * Hindi LITERATURE IS GONE — the old file's two compound entries listing 12
    poets and 11 prose writers appear nowhere in the 2026 text.
  * Hindi बोलियाँ is now "पूर्वी हिंदी, पश्चिमी हिंदी तथा पहाड़ी" — the explicit
    "कुमाउनी, गढ़वाली, जौनसारी" naming is gone.
  * Computer gained AI, Data Science, ML, IoT, Blockchain, Cloud, Big Data,
    Edge Computing, Generative AI, AR/VR, Green Computing, OSI model, HTML.
  * Uttarakhand is 8 bullets in the source (the old file had 44 derived ones).
  * Not found in the 2026 source, dropped: "राजस्व पुलिस व्यवस्था",
    "जमींदारी उन्मूलन एवं भूमि बन्दोबस्त".
"""
from __future__ import annotations

# ── exam families on the master syllabus ─────────────────────────────────────
# blueprint.SUBJECT_MIX keys. Any exam family listed here gets official-
# syllabus topic seeding in exam mode.
MASTER_SYLLABUS_EXAMS = {
    "vdo-vpdo", "lekhpal-patwari", "group-c", "police-constable",
}

# ── the official taxonomy, per corpus subject ────────────────────────────────

TOPICS: dict[str, list[str]] = {
    # ── 01 सामान्य हिंदी — 20 अंक (source "Page 2 of 7") ────────────────────
    # 12 official bullets, transcribed as written. NOTE: the 2026 syllabus has
    # NO literature component — no poet/prose-writer lists.
    "hindi": [
        "भाषा एवं हिंदी भाषा: भाषा के प्रकार, हिंदी भाषा का विकास, हिंदी भाषा के विविध रूप, कार्यालयी हिंदी, हिंदी की बोलियाँ (पूर्वी हिंदी, पश्चिमी हिंदी तथा पहाड़ी)",
        "देवनागरी लिपि: देवनागरी लिपि का विकास, देवनागरी लिपि की विशेषताएं, देवनागरी लिपि में लिखी जाने वाली भारतीय भाषाएं",
        "हिंदी वर्ण एवं ध्वनि विचार: वर्ण, अक्षर, स्वर, व्यंजन, मात्रा, ध्वनियों का वर्गीकरण",
        "हिंदी वर्तनी: वर्तनी विश्लेषण, शुद्ध-अशुद्ध वर्तनी, विराम चिह्न, हिंदी वर्तनी का मानकीकरण, हिंदी अंक",
        "शब्द संरचना: संज्ञा, सर्वनाम, विशेषण, क्रिया-विशेषण, क्रिया, लिंग, वचन, पुरुष, काल, कारक, उपसर्ग, प्रत्यय, समास",
        "शब्द भंडार: तत्सम, तद्भव, देशज, आगत (भारतीय एवं विदेशी भाषाओं से हिंदी में आए प्रचलित शब्द), एकार्थी, अनेकार्थी, विपरीतार्थी (विलोम), पर्यायवाची",
        "संधि एवं संधि विच्छेद",
        "वाक्य परिचय: वाक्य की परिभाषा, वाक्य के अंग, वाक्य के प्रकार, वाक्य-शुद्धि",
        "मुहावरे एवं लोकोक्तियां",
        "पत्र लेखन: टिप्पण, प्रारूपण, विज्ञप्ति, सरकारी एवं अर्द्धसरकारी पत्र",
        "जनसंचार के विभिन्न माध्यम",
        "हिंदी में कंप्यूटर का अनुप्रयोग",
    ],

    # ── 2.1 सामान्य बुद्धि परीक्षण एवं तर्कशक्ति (source "Page 3 of 7") ──────
    # NEW 2026-09-10. Not in the previous file at all. No corpus, no
    # SUBJECT_MIX entry — see module docstring. Prefixed A-/B- exactly as the
    # source splits them, because the two halves need DIFFERENT generators:
    # verbal = pure text (no RAG, no figures); non-verbal = code-drawn figures.
    "reasoning": [
        # A — Verbal Reasoning / मौखिक तर्कशक्ति
        "Alphabetical Test (वर्णमाला परीक्षण)",
        "Coding-Decoding (कूटलेखन-कूटवाचन)",
        "Analogy (सादृश्यता)",
        "Order Arrangement (क्रम व्यवस्था)",
        "Blood Relations (रक्त संबंध)",
        "Classification (वर्गीकरण)",
        "Word Formation (शब्द निर्माण)",
        "Direction & Distance (दिशा एवं दूरी)",
        "Venn Diagram (वेन आरेख)",
        "Calendar (कैलेंडर)",
        "Problem Solving (समस्या समाधान)",
        "Puzzles (पहेलियाँ)",
        "Seating Arrangement (बैठक व्यवस्था)",
        "Logical Reasoning (तार्किक तर्कशक्ति)",
        "Data Sufficiency (डेटा पर्याप्तता)",
        "Mathematical Operations (गणितीय संक्रियाएँ)",
        # B — Non-Verbal Reasoning / अमौखिक तर्कशक्ति
        "Classification — अमौखिक (वर्गीकरण)",
        "Figure Counting (आकृति गणना)",
        "Figure Completion (आकृति पूर्ण करना)",
        "Grouping of Identical Figures (समान आकृतियों का समूह)",
        "Mirror Image (दर्पण प्रतिबिंब)",
        "Water Image (जल प्रतिबिंब)",
        "Paper Folding & Cutting (कागज़ मोड़ना एवं काटना)",
        "Cube & Dice (घन एवं पासा)",
        "Figure Analogy (आकृति सादृश्य)",
        "Analytical Figure Reasoning (विश्लेषणात्मक आकृति तर्क)",
    ],

    # ── 2.2-2.6 सामान्य ज्ञान एवं सामान्य अध्ययन — इतिहास / भूगोल /
    # राजनीति विज्ञान / अर्थशास्त्र / समसामयिक (source "Page 3-5 of 7").
    # The source gives these as broad paragraph-bullets per discipline, not as
    # itemised lists — transcribed as written, one entry per official bullet.
    "general-gk": [
        # 2.2 इतिहास
        "प्राचीन भारत (हड़प्पा सभ्यता से 1206 ईस्वी तक) का राजनैतिक, सामाजिक, आर्थिक एवं सांस्कृतिक इतिहास, प्रशासनिक व्यवस्था, बौद्ध एवं जैन धर्म",
        "मध्यकालीन भारत का राजनैतिक, सामाजिक, आर्थिक एवं सांस्कृतिक इतिहास, प्रशासनिक व्यवस्था, भक्ति एवं सूफी आंदोलन",
        "आधुनिक भारत का इतिहास: यूरोपीय कंपनियों का आगमन, साम्राज्य स्थापना एवं विस्तार, आर्थिक एवं प्रशासनिक नीतियाँ, प्रमुख विद्रोह, प्रमुख अधिनियम, सामाजिक एवं धार्मिक सुधार आंदोलन, भारत का स्वतंत्रता संघर्ष, भारत का विभाजन एवं स्वतंत्रता के बाद की प्रमुख घटनाएं",
        "विश्व इतिहास की प्रमुख घटनाएँ: औद्योगिक क्रान्ति, यूरोप में पुनर्जागरण, अमेरिका का स्वतंत्रता संग्राम, फ्रांसीसी क्रांति, रूसी क्रांति, प्रथम व द्वितीय विश्व युद्ध",
        # 2.3 भूगोल
        "भारत का भूगोल: भौगोलिक परिचय, उच्चावच, जलवायु, प्रवाह प्रणाली",
        "भारत के संसाधन: प्राकृतिक वनस्पति, मृदा, जल, खनिज एवं ऊर्जा",
        "भारत: बहुउद्देशीय नदी घाटी परियोजनाएँ, फसलें, जनसंख्या, जनजातियाँ",
        "भारत में पर्यावरणीय संकट: वायु, जल एवं मृदा प्रदूषण",
        "विश्व का भूगोल: सौर मंडल की उत्पत्ति, अक्षांश-देशान्तर, उच्चावच, चट्टानें",
        "विश्व का भूगोल: समुद्री धाराएं, लवणता, ज्वार भाटा, जलवायु एवं प्रमुख वायुमंडलीय घटनाएं",
        "विश्व का भूगोल: प्रमुख फसलें, प्रमुख उद्योग, जनसंख्या और जनजातियां",
        # 2.4 राजनीति विज्ञान
        "भारत में राष्ट्रीय जागृति और सामाजिक-धार्मिक पुनर्जागरण (महत्वपूर्ण नेता, संगठन और घटनाएँ), भारतीय राष्ट्रीय आंदोलन के दौरान महत्वपूर्ण चरण और विभिन्न आंदोलन",
        "गांधीवाद, भारत के संविधान की मुख्य विशेषताएँ, मौलिक अधिकार, मौलिक कर्तव्य, राज्य के नीति निदेशक तत्व, भारत के संविधान में अनुसूचित जाति, अनुसूचित जनजाति और अन्य पिछड़ा वर्ग से संबंधित प्रावधान",
        "भारत की संसद, भारत का सर्वोच्च न्यायालय, भारत में राजनीतिक दल और चुनावी प्रक्रिया, भारत में सूचना का अधिकार, स्थानीय स्वशासन की अवधारणा, उत्तराखंड में पंचायती राज से संबंधित अधिनियम और प्रावधान",
        "संयुक्त राष्ट्र संघ (इसकी कार्यप्रणाली और विभिन्न अंग), वैश्वीकरण की अवधारणा, मानव अधिकार, पर्यावरण, शस्त्रीकरण और दक्षिण-एशिया के मुद्दों से संबंधित विषय",
        # 2.5 अर्थशास्त्र
        "भारतीय अर्थव्यवस्था की विशेषतायें, जनांकिकीय प्रवृत्तियाँ",
        "भारतीय कृषि की विशेषतायें: उत्पादन एवं विपणन, कृषि सुधार, खाद्य सुरक्षा",
        "औद्योगिक विकास एवं समस्याएँ, लघु उद्योग, सूक्ष्म-लघु एवं मध्यम उद्योग — विकास व समस्यायें, औद्योगिक नीति",
        "'नीति' आयोग, मुद्रा एवं वित्त, नई आर्थिक नीति",
        "गरीबी निवारण एवं रोजगार सृजन कार्यक्रम, सामाजिक सुरक्षा योजनायें, मानव विकास, सतत् विकास लक्ष्य (SDGs)",
        "भारतीय संघीय व्यवस्था एवं कर प्रणाली",
        "भारत का विदेशी व्यापार: प्रवृत्ति एवं दिशा, भुगतान संतुलन, विदेशी व्यापार नीति, विश्व व्यापार संगठन",
        # 2.6 समसामयिक घटनाएँ
        "भारत: राज्यों से संबंधित जानकारी, राष्ट्रीय प्रतीक, भौगोलिक जानकारी, महत्वपूर्ण स्थान, भाषा और साहित्य, खेल और संबंधित शब्दावली, पुरस्कार, महत्वपूर्ण योजनाएँ एवं अन्य समसामयिक घटनाक्रम",
        "अंतर्राष्ट्रीय: महत्वपूर्ण खोजें/आविष्कार/तकनीकी प्रगति, महत्वपूर्ण वैश्विक सूचकांक/रिपोर्ट, महत्वपूर्ण संगठन एवं अन्य समसामयिक घटनाक्रम",
    ],

    # ── 2.7 कंप्यूटर का आधारभूत ज्ञान (source "Page 5-6 of 7") ──────────────
    # 6 official bullets. The 2026 revision added a whole emerging-tech bullet
    # (AI/ML/IoT/blockchain/cloud/big data/edge/GenAI/AR-VR/green computing)
    # that the previous file predated entirely.
    "computer": [
        "कंप्यूटर फ़ंडामेंटल्स: कंप्यूटर बेसिक्स, सॉफ्टवेयर, एल्गोरिद्म, फ़्लोचार्ट्स तथा प्रोग्रामिंग लैंग्वेजेज़",
        "ऑपरेटिंग सिस्टम्स: ऑपरेटिंग सिस्टम की कॉन्सेप्ट्स, ओपन-सोर्स एवं प्रोप्राइटरी ऑपरेटिंग सिस्टम्स, विंडोज़ के फ़ीचर्स, कीबोर्ड शॉर्टकट्स, सॉफ़्टवेयर इंस्टॉलेशन एवं रिमूवल, कंट्रोल पैनल, सिस्टम टूल्स तथा लिनक्स बेसिक्स",
        "ऑफिस ऑटोमेशन टूल्स: वर्ड प्रोसेसिंग, स्प्रेडशीट, प्रेज़ेंटेशन सॉफ्टवेयर",
        "कंप्यूटर नेटवर्क्स: नेटवर्क की कैरेक्टरिस्टिक्स, नेटवर्क के टाइप्स, नेटवर्क टोपोलॉजीज़ तथा नेटवर्क कॉम्पोनेंट्स, OSI मॉडल",
        "इंटरनेट एवं वेब प्रोग्रामिंग: इंटरनेट, वर्ल्ड वाइड वेब, आईपी एड्रेस, यूआरएल, डोमेन नेम, ईमेल, वेब ब्राउज़र, सर्च इंजन, इंटरनेट प्रोटोकॉल, वेबसाइट एवं वेब पेज, एचटीएमएल के आधारभूत सिद्धांत",
        "साइबर सिक्योरिटी एवं इमर्जिंग टेक्नोलॉजीज़: साइबर सिक्योरिटी, साइबर थ्रेट्स, भारतीय आईटी एक्ट, फ़ायरवॉल्स, कुकीज़, आर्टिफ़िशियल इंटेलिजेंस, डेटा साइंस, मशीन लर्निंग, इंटरनेट ऑफ थिंग्स, ब्लॉकचेन, क्लाउड कंप्यूटिंग तथा बिग डेटा, एज कंप्यूटिंग, जेनेरेटिव एआई, ऑगमेंटेड रियलिटी, वर्चुअल रियलिटी, ग्रीन कम्प्यूटिंग",
    ],

    # ── 2.8 उत्तराखण्ड का सामान्य ज्ञान — 40 अंक (source "Page 6-7 of 7") ──
    # The source gives EIGHT bullets, not a per-discipline breakdown. They are
    # transcribed verbatim and assigned to the corpus subject that owns the
    # material — the only reorganisation this file still performs, because
    # book_passages is partitioned by these four subjects.
    #
    # Two bullets legitimately span subjects and are therefore split at the
    # semicolon the source itself uses; nothing is added or reworded.
    "uk-geography": [
        "उत्तराखंड का भौगोलिक परिचय: स्थिति और विस्तार, पर्वत चोटियाँ, हिमनद, नदियाँ, झीलें। संसाधन - वन, राष्ट्रीय उद्यान और अभयारण्य, मृदा, कृषि और जनसंख्या",
        "उत्तराखंड में जैव-विविधता, जल संसाधन, पर्यावरण, पारिस्थितिक स्थितियाँ, प्रदूषण और आपदा प्रबंधन",
    ],
    "uk-history": [
        "उत्तराखंड का इतिहास: महत्वपूर्ण राजवंश (कत्यूरी, चंद, पंवार और गोरखा), ब्रिटिश शासन, भारतीय स्वतंत्रता संग्राम के परिप्रेक्ष्य में उत्तराखंड, उत्तराखंड के प्रमुख स्वतंत्रता सेनानी और प्रसिद्ध व्यक्तित्व, महत्वपूर्ण सामाजिक आंदोलन और उत्तराखंड राज्य गठन आंदोलन",
    ],
    "uk-culture": [
        "उत्तराखंड का सांस्कृतिक पक्ष, परंपराएँ और महत्वपूर्ण स्थल",
    ],
    "uk-general-studies": [
        "उत्तराखंड की अर्थव्यवस्था: कृषि और संबद्ध क्षेत्र, प्रमुख उद्योग, पर्यटन, महत्वपूर्ण सांख्यिकीय आँकड़े, रोज़गार, महत्वपूर्ण संस्थान, प्रमुख परियोजनाएँ और योजनाएँ",
        "उत्तराखंड में सामान्य राजव्यवस्था और प्रशासनिक व्यवस्था, स्थानीय स्वशासन और महत्वपूर्ण पहल",
        "उत्तराखंड में शिक्षा: महत्वपूर्ण संस्थान और प्रमुख नीतिगत पहल",
        "उत्तराखंड से संबंधित समसामयिकी",
    ],
}


# topics_for() lived here until 2026-09-13 — ARCHIVED to
# .archive/dsideos-dead-code/, zero callers. It fed these bullets to the
# generator as "topics", but a bullet is a SECTION HEADING, not a question-
# sized topic. Phase 2 does that job properly: worker/taxonomy_data/ holds
# hand-authored trees decomposing each bullet below into question-sized
# leaves, sampled by worker/taxonomy.py.
#
# THIS FILE IS NOT DEAD. The TOPICS dict above is the canonical transcription
# of the official UKSSSC 2026 syllabus and is what the taxonomies were
# authored FROM — reference data, and the thing to check a taxonomy against.
