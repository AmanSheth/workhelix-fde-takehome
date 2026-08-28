This document serves as a write up for the design process I went through and the decisions I made. 

Architecturally, the system is built around a shared data model rather than one monolithic detector: a PIILabel enum for the six categories, and a Span (start, end, label) that every detector returns regardless of what technique it uses internally. Detection is split into six independent functions, one per category, and each one uses whatever approach actually fits that category rather than forcing a single strategy across all of them — regex for EMAIL, PHONE_NUMBER, SSN, and DATE_OF_BIRTH, spaCy's NER model plus a small regex pass for PERSON_NAME, and a two-part regex (a required core plus an optional tail) for STREET_ADDRESS. A single detect() function runs all six and then does two kinds of cleanup on the combined output: general span hygiene that applies no matter which detector produced a span (clipping anything that accidentally crosses a line break, trimming stray whitespace), and one cross-category rule that uses the address detector — which is reliable — to veto PERSON_NAME hits that fall inside an already-detected address, since that turned out to be a real, recurring source of false positives (street names and city names getting misread as people's names). redact() sits on top of detect() and is the actual service entry point described in the brief: it takes the spans and splices [LABEL] placeholders into the text, returning both the redacted text and the underlying spans. Everything else is plumbing around that core: predict.py is a batch driver that runs detect() over a dataset file and writes predictions in the format evaluate.py expects, and redactor.py also exposes a small CLI (python redactor.py "some text", or piped via stdin) for running the service directly against one string — which is what I'd use to demo it live, rather than only running it over the fixed sample dataset.

First approach that came to mind was to use Regex. This is maybe the "traditional" path for standard pattern matching. 

This works quite well for SSNs, Phone Numbers and Email Addresses, albeit with some noted holes. This brings us to a pretty big decision: structure. 


Decision 1: Structure

A phone number is really nothing more than 10 numbers with an optional country code prefix. It is usually presented in a 3-3-4 pattern, with some kind of divider between the groups (parentheses,periods,dashes) but not always. The same is true for SSNs with a 3-2-4 pattern. In the case that there is no structure, there is almost nothing identifying a X-digit sequence as a phone number or SSN vs a random ID or other generic number string. As such, I made a decision that for phone numbers, the redactor searches for  structure when looking for phone numbers. There is a phone number library in Python that would do the same, but with the additional functionality of validating that the number is actually a registered phone number, allowing for the finding of non-separated numbers without adding false positives. I considered using this instead, but I worried that the testing data might include non-valid numbers that are shaped like phone numbers, which this library would then reject (yielding an inaccuracy, just in the context of this excersise). No such equivalent library exists for SSNs, so I implemented a two tiered system: a first pass that looks for structured, separated SSNs, and another pass that looks for any 9 digit string that appears close to keywords like "SSN" or "Social Security Number". This way a random 9-digit string won't be hit as a false positive unless it's in proximity to a keyword. The yielded result means that there is almost no chance for false positive phone numbers or ssn, and some small chance of false negatives in the case that the string is unstructured. Applying the library would remove all false negative Phone Number cases, and further improving the keyword list would improve the rate of false negative SSNs. A further step could be to implement an LLM and I'll discuss that further in the LLM decision section. 

DOB is next, and is pretty simple. Dates are usually structured (month/day/year or Day of Month, Optional Year). Writing regex patterns to catch these is easy, the hard part is differentiating birthdates from any other kind of date. This is a context problem, rather than a detection problem, and in this case I solved it by using the same strategy I adopted for SSNs. I look for some keywords ("birthday", "dob", "birth date") and search around them for dates matching the regex patterns. This works in our sample data, but has some potential holes for false negatives in practical data. I think again an LLM could be used here, that I'll discuss in the later section. 

The next two pieces of PII are more complicated. I'll start by discussing addresses. I opted into using standard Regex with a pretty sizeable pattern instead of using an LLM for reasons that I'll discuss later on. The pattern is pretty straightforard, some number of digits, followed by up to 3 capitalized words, ending in a "Street" name (this is a collection of common street monikers I found), then a suite/apartment number, comma, city, comma, state, zipcode. The later half are all individually optional and the redactor greedily searches for them once it hits on the first half. An important note is that in order to stop the redactor from consuming past the address, it stops when it hits a newline or a non-comma punctuation. This is fine for the purposes of the training data I was given but again could potentially produce false negatives in the future if the address is separated accross lines or includes a street name like "St. Mary's Street". It also produces false negatives for uncommon street names like "Crescent". Again I think an LLM could be implemented here, and I'll discuss that in the later section. 

Names are the hardest piece of PII to detect. Just checking for capitalized words doesn't work as organizations, locations, and brands fit into this pattern and would be false positives. More over, names can be unusual, and using a corpus of known names isn't effective if the actual data isn't "western". As such, I needed to approach this from a context perspective. The approach I settled on was using spaCy entity detection to find and label "entities" in the text, and then pull the ones it determines are "people". This is done using a locally downloaded model that looks at the shape of the text to determine what is an entity and what is not. We then take any given results and expand them using Regex to look for prefixes and suffixes (Mr., Dr., Jr., Sr., etc). The chosen model is effective on the given dataset, but may or may not be fully accurate on future datasets. It also does struggle sometimes with data where names aren't provided in context (like in terse label:name contexts), or occasionaly detect city names as people names (Austin, Dallas, etc.). For the first, I think in production we'd create some kind of upstream categorization of document type so that the redactor can adjust it's approach based on what kind of data it's taken in. For the address problem, I've implemented a specific pass through the spans to make sure there's no overlap between names and addresses. This is probably a good time to talk about the LLM decision. 

Decision 2: LLMs

When seeing this problem, clearly a frontier model LLM would solve this issue very quickly. However, by the nature of PII being protected, the client obviously can't send out the data to systems it doesn't control. The natural next option would be to use a locally hosted model (like Ollama), and run the text through that. This was an approach that I tried with a couple of models and came to the following conclusions. Primarily, I don't think there's a reason to use LLMs for emails or phone numbers, these are both fundementally solved problems, where an LLM would be slower and more expensive for no marked improvement in accuracy. I think an LLM would help with the bare SSN and date distinguishing problems I've discussed previously. We could run the regex to detect all SSN-like or Date-like strings and then pass their local contexts into an LLM to make a call on whether or not this is actually an SSN/Birthdate. Addresses could be done the same way, pass matched regex into the LLM and let it figure out the entire scope of the address to redact. Names would work differently, we'd need to give the entire text into the LLM and let it look for names. The issues with an LLM here are the usual suspects: cost, time, non-determinism, and required human verification. 

I'll start by discussing how an LLM system would work, and why it might be better, and then discuss why I chose not to use it here.

An ideal LLM here would be some off-the-shelf open source model (Qwen or Ollama come to mind), hosted locally, and fine-tuned on data specific to this problem (I'll discuss why this step is crucial a little later). Then we'd use it as a kind of validator, a matched regex pattern could be fed into the LLM along with the surrounding context, and it would parse whether or not it is a valid piece of PII. Then it would present it's findings to a human, along with a confidence metric (maybe we'd just limit to showing the human the hits it's less confident about), and we'd get human validation for each. This would fix all of the holes in our current strategy, and would be my approach for a production system but is untenable for this excerise. 

I tried using two off the shelf models for this problem (an 800mb Google model, and a 5gb llama model) and found that without fine tuning, the smaller model was less accurate than our current system and the bigger model was exactly the same level of accuracy. I synthesized a bigger dataset from the given dataset using an LLM, and found the same holds with the smaller model on a bigger dataset, and the bigger model ran into another big problem. Our current system is fast, regex parsing is linear time, and relatively computationally cheap, the 10 line file is done in under a second, while the larger 100 line file is done in just a few seconds. The bigger LLM took far longser, each line took about a minute, meaning the given 10 line data took 10 minutes to parse, and the bigger file I generated would have taken almost 2 hours. This could be sped up with better hardware (I was running on my macbook, in production it would be done on a server with a GPU), but even then it would still undoubtedly be several times slower. Moreover, neither LLM provided any improvement in accuracy, at least off the shelf. To improve their results we'd need to finetune, which can't be done with the limited dataset I currently have. In production, both of these issues could be mitigated, meaning an LLM would almost certainly be the way to go. 

SOME NOTES:

This is the output for the given dataset:
Wrote predictions for sample_dataset.jsonl to predictions.jsonl
=== SAMPLE DATASET (10 rows) ===
======================================================================
PII REDACTION EVALUATION REPORT
======================================================================
Mode: IoU >= 0.5 (label must match)

Per-category metrics:
Category                TP    FP    FN   Recall     Prec       F1
----------------------------------------------------------------------
DATE_OF_BIRTH            6     0     0    1.000    1.000    1.000
EMAIL                   11     0     0    1.000    1.000    1.000
PERSON_NAME             14     1     0    1.000    0.933    0.966
PHONE_NUMBER             9     0     0    1.000    1.000    1.000
SSN                      4     0     0    1.000    1.000    1.000
STREET_ADDRESS           5     0     0    1.000    1.000    1.000

Overall (macro-averaged across categories):
  Recall:    1.000
  Precision: 0.989
  F1:        0.994

Totals: 49 TP, 1 FP, 0 FN
  Ground truth spans: 49
  Predicted spans:    50

This is the data for when I tried using the Llama model:
llama3.1:8b (naive): 10-row F1  = 0.966 (matches spaCy exactly) at ~73s/doc vs spaCy's milliseconds (PERSON_NAME ONLY)


This is on the bigger dataset (self made):
Overall (macro-averaged): Recall 0.998, Precision 0.989, F1 0.993
Totals: 488 TP, 10 FP, 2 FN
All errors are names. 


The expanded dataset maintains the same structure as each of the rows on the original, but creates new PII to be substituted in. This is an effective way to test the bounds of specific detectors (Name, Address), but doesn't test in new contexts. I concluded that trying to generate new contexts would be out of the scope of this excerise, as I would really just be guessing, and thus could taint my approach. 