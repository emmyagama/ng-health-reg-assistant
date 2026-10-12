Observations grounded in retrieval_test_10.csv
1. Only one question wasn't rank-1, and it's a genuine topic-overlap case between two Acts.
Q3 ("Basic Health Care Provision Fund…") returned national_health_act_2014 at rank 1 and nhia_act_2022 only at rank 2, with the top-5 split as:
text
national_health_act_2014; nhia_act_2022; nhia_act_2022; national_health_act_2014; national_health_act_2014
So 3 of 5 slots are national_health_act_2014 and only 2 are the expected nhia_act_2022. What's in the data: the exact phrase "Basic Health Care Provision Fund" appears in both acts — the 2014 Act established the fund; the 2022 NHIA Act operationalises it under the Vulnerable Group Fund. The 2014 Act chunk(s) carry stronger lexical overlap with the exact question phrasing, which pushes them above the 2022 Act. This is a nearest-neighbour tie between sister documents, not a failure to find the topic.
2. The dominant pattern across the top-5 is heavy same-document duplication — chunks from the same doc crowding out diversity.
Counting how many of the 5 slots come from the winning doc per question:
Q	Expected doc	Slots occupied by that doc	Other docs in top-5
1	hefamaa_requirements	1/5	nhia_guidance_2023 (×2!), mlscn_guidelines, who_lab_quality_guidance
2	mlscn_guidelines	4/5	who_lab_quality_guidance
3	nhia_act_2022	2/5	national_health_act_2014 (×3)
4	ndpa_2023	4/5	ndpc_guidance_2024
5	ndpc_guidance_2024	3/5	ndpa_2023 (×2)
6	national_health_act_2014	5/5	(none)
7	nhia_guidance_2023	3/5	nhia_act_2022 (×2)
8	who_lab_quality_guidance	4/5	mlscn_guidelines
9	national_health_act_2014	5/5	(none)
10	ndpa_2023	5/5	(none)
Five questions return the expected doc in all 5 slots (Q6, Q9, Q10) or 4 of 5 (Q2, Q8). Q1 is the only one with real diversity — but it has its own oddity: nhia_guidance_2023 appears twice at positions 2 and 4, meaning the same doc is being retrieved under two different chunks rather than the other 3 slots being populated by distinct documents. The downstream generator is therefore being fed 4–5 near-duplicate passages from a single section instead of multiple perspectives.
3. Acts and their corresponding guidance documents are competing head-to-head on 4 of 10 questions, with rank flips visible.
Whenever an Act and a regulatory guidance document cover the same topic, both appear in the top-5 and the order depends on which has the closer lexical match to the question phrasing:
•	Q4 (data-controller obligations): Act (ndpa_2023) wins rank 1; the matching guidance (ndpc_guidance_2024) is rank 2.
•	Q5 (NDPC fees): guidance (ndpc_guidance_2024) wins rank 1 (correct — fees live in the guidance), but the Act (ndpa_2023) still takes slots 4–5.
•	Q7 (CSHIS): guidance (nhia_guidance_2023) wins rank 1; the Act (nhia_act_2022) is at 2 and 5.
•	Q3 (BHCPF): as noted, the older Act (national_health_act_2014) beats the expected nhia_act_2022 for rank 1.
The pattern in the data: doc pairs that share a topic (Act↔Guidance) are consistently within ~0.05–0.1 distance of each other, so minor differences in chunk wording decide the rank.
4. Three of the doc_ids in Chroma don't match the actual source PDF filenames from your corpus.
Comparing the doc_ids appearing in the returned_doc_ids column to the files I noted in corpus_structure_notes.md:
Source PDF	doc_id in Chroma (from CSV)
hefamaa_quickguide.pdf	hefamaa_requirements
nhia_operational_guidelines_2023.pdf	nhia_guidance_2023
who_lqms_handbook.pdf	who_lab_quality_guidance
(Golden-set expected_doc_id for Q1 is hefamaa_requirements, which matches the Chroma ID but not the raw filename.) The golden set happens to line up with what's stored, so accuracy is reported as 100% — but the renamed IDs mean the evaluation is brittle: any future re-ingestion that uses doc_id = filename_stem will immediately break the golden set for these three documents, producing false "misses". It also explains why Q1 returns nhia_guidance_2023 as a near neighbour rather than a document about HEFAMAA — under the shortened ID nhia_guidance_2023 there is some shared vocabulary (registration, facility, accreditation) with the HEFAMAA question.
5. Question 1 is the weakest result overall even though it "passed".
Q1's top-5 is:
text
hefamaa_requirements; nhia_guidance_2023; mlscn_guidelines; nhia_guidance_2023; who_lab_quality_guidance
Only 1 of 5 chunks is actually from the HEFAMAA doc; positions 2 and 4 are the same wrong doc (nhia_guidance_2023, repeated), and 3/5 slots are docs covering laboratory standards/quality/WHO guidance that aren't directly about HEFAMAA accreditation. This is the question most likely to produce a poor generated answer even though top-1 accuracy is "correct", because the model is being given 4 mostly irrelevant context chunks plus only one relevant chunk.
________________________________________
Bottom line, from the data only
•	No hard failures (10/10 hit top-5).
•	One borderline ranking (Q3, where the 2014 Act edges out the 2022 NHIA Act for BHCPF) — caused by both documents legitimately discussing the same fund.
•	Systemic issue: across 8 of 10 questions, 4–5 of the 5 retrieved slots come from a single document (often with repeat chunks), so the retriever is favouring the nearest chunk's siblings over diverse cross-document evidence. Q1 is the extreme case: only 1/5 slots is the right doc, and one wrong doc appears twice.
•	Naming hygiene issue: three doc_ids in Chroma (hefamaa_requirements, nhia_guidance_2023, who_lab_quality_guidance) don't match the actual filenames, which makes the golden-set/ingestion coupling fragile even though current accuracy is 100%.