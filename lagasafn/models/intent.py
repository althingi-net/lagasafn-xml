from enum import Enum
from pydantic import BaseModel
from pydantic import Field

# https://platform.openai.com/docs/guides/structured-outputs?lang=python
# https://community.openai.com/t/how-to-define-pydantic-json-schema/988192/5

class IntentActionEnum(Enum):
    ADD = "add"
    EDIT = "edit"
    DELETE = "delete"
    UNKNOWN = "unknown"
    NONE = ""

class IntentSubjectAdded(Enum):
    TEMP_CLAUSE = "temp_clause"

class IntentModel(BaseModel):
    action: IntentActionEnum = Field(
        ...,
        description="This will be the string 'add', 'edit' or 'delete', depending on whether the input instructs addition, change or deletion content in existing laws. Must be empty if the input instructs no such modifications, but 'unknown' if not certain."
    )
    #subject_added_type = IntentSubjectAddedType = Field(
    #    ...,
    #    description="This is the type of content being added."
    #)
    #subject_added_content: str = Field(
    #    ...,
    #    description="When the action is to add content, this is the content being added in XML form."
    #)
    target_location: str = Field(
        ...,
        description="The location within the target law where the dictated modifications will take place. Example strings: 'Ákvæði til bráðabirgða', '5. tölul. 3. mgr. 6. gr.'."
    )
