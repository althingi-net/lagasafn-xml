# Backward compatibility - import from new law module structure
from lagasafn.law.compatibility import Law, LawManager

# Also export the new models for gradual migration
from lagasafn.law.models.law_entry import LawEntry
from lagasafn.law.models.law_document import LawDocument  
from lagasafn.law.models.law_index import LawIndex
from lagasafn.law.models.law_index_info import LawIndexInfo

