Meðfylgjandi XML skjal lýsir breytingum á lögum nr. {affected-law-nr}/{affected-law-year}.

Skrifaðu fyrir mig XML skrá með rótarmerkinu "intent".

Settu inn í hana eftirfarandi merki:

"action": Segir til um hvort greinin bæti efni við, breyti því, skipti því út eða eyði. Hér skal setja "add" ef efni er bætt við, "change" ef því er breytt, "replace" ef því er skipt út og "delete" ef því er eytt. Efninu er skipt út ef það "orðast svo". Ef óljóst, skaltu setja "unclear".

"structure-type": Tilgreinir tegund þess efnis sem er bætt við eða breytt. Málsliðir verða "sen", málsgreinar verða "subart" og greinar verða "art".

"location": Nákvæm staðsetning breytingarinnar innan samhengis laganna. Ef breytingin felur í sér nýja staðsetningu fyrir efnið, settu nýju staðsetninguna inn í nýtt merki sem heitir "location-new".

"text-from": Ef texta er breytt, settu hér inn þann texta sem á að breyta. Slepptu annars merkinu.

"text-to": Ef texta er breytt, settu hér inn textann eins og hann á að vera eftir breytinguna. Slepptu annars merkinu.

"text": Ef texta er bætt við, settu hér textann sem á að bæta við. Slepptu annars merkinu.

Ef grein inniheldur fleiri en eina breytingu, en þó einungis ef grein inniheldur fleiri en eina, gerðu eftirfarandi: Settu inn merkið "common" með eigindinu "location" sem inniheldur staðsetninguna sem allar breytingarnar eiga sameiginlegar. Settu síðan hverja breytingu inn í úttaksskjalið sem sérstakt "intent" merki með eigindinu "nr" fyrir staflið hverrar breytingar.

Birtu úttakskrána sem hreina XML skrá, án neinna skýringa.
