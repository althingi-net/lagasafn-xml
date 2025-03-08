from enum import Enum
from pydantic import BaseModel
from pydantic import Field
from typing import List

# https://platform.openai.com/docs/guides/structured-outputs?lang=python
# https://community.openai.com/t/how-to-define-pydantic-json-schema/988192/5

class IntentActionEnum(Enum):
    ADD = "add"
    EDIT = "edit"
    DELETE = "delete"
    REPLACE = "replace"
    UNKNOWN = "unknown"
    NONE = ""

class IntentSubjectAdded(Enum):
    TEMP_CLAUSE = "temp_clause"

class IntentModel(BaseModel):
    nr: str = Field(
        ...,
        description="Ef greinin felur í sér margar breytingar, settu inn staflið hverrar breytingar hér. Skal annars vera tómt."
    )
    action: IntentActionEnum = Field(
        ...,
        description='Segir til um hvort greinin bæti efni við, breyti því, skipti því út eða eyði. Hér skal setja "add" ef efni er bætt við, "change" ef því er breytt, "replace" ef því er skipt út og "delete" ef því er eytt. Efninu er skipt út ef það "orðast svo". Ef óljóst, skaltu setja "unknown".'
    )
    structure_type: str = Field(
        ...,
        description='Tilgreinir tegund þess efnis sem er bætt við eða breytt. Málsliðir verða "sen", málsgreinar verða "subart" og greinar verða "art". Ef óljóst, settu "unknown".'
    )
    location_common: str = Field(
        ...,
        description='Ef greinin í inntakinu er sundurliðuð niður í stafliði eins og "a", "b", "c" o.s.frv., skaltu setja hér inn staðsetninguna sem þær eiga sameiginlegar. Annars skal þetta vera tómt.'
    )
    location: str = Field(
        ...,
        description='Staðsetningin þar sem breytingin á að eiga sér stað. Ekki tilgreina lögin sjálf, ekki heldur með strengnum "laganna".'
    )
    location_new: str = Field(
        ...,
        description="Ef efni er bætt við á nýjan stað, fer ný staðsetning nýja efnisins hingað. Skal annars vera tómt."
    )
    text_from: str = Field(
        ...,
        description="Ef texta er breytt og það kemur fram hver textinn er fyrir breytinguna, settu inn textann eins og hann var fyrir breytingu. Skal annars vera tómt."
    )
    text_to: str = Field(
        ...,
        description="Ef texta er breytt eða bætt við, settu hér inn textann eins og hann á að vera eftir breytinguna. Skal annars vera tómt."
    )


class IntentModelList(BaseModel):
    items: List[IntentModel] = Field(
        ...,
        description="Listi af breytingum sem greinin lýsir."
    )
