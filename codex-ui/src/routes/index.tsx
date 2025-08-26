import { createSignal, createResource, createMemo } from "solid-js";
import { LawService } from "~/api";
import Header from "~/components/Header";
import LawStats from "~/components/LawStats";
import LawTable from "~/components/LawTable";

interface Law {
  nr: string;
  name: string;
  chapter?: number;
  article?: number;
  status: 'OK' | string;
}

// Dummy data matching the image format
const DUMMY_LAWS: Law[] = [
  { nr: "6/2025", name: "Forsetaúrskurður um skiptigu starfa ráðherra", chapter: 12, status: "OK" },
  { nr: "5/2025", name: "Forsetaúrskurður um skiptigu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands", chapter: 13, status: "OK" },
  { nr: "4/2025", name: "Forsetaúrskurður um skiptigu Stjórnarráðs Íslands í ráðuneyti", chapter: 0, status: "OK" },
  { nr: "130/2024", name: "Lög um stuðningsáætli til rekstraraðila í Grindavíkurbæ vegna jarðhræringa á Reykjanesskkaga", chapter: 17, status: "OK" },
  { nr: "126/2024", name: "Lög um heimild fyrir ríkisstjórnina til að samþykkja hækkun á kvóta Íslands hjá Alþjóðagjaldeyrissjóðnum", chapter: 2, status: "OK" },
  { nr: "111/2024", name: "Lög um Náttúruverndarstoufun", chapter: 1, article: 6, status: "OK" },
  { nr: "110/2024", name: "Lög um Umhverfis- og orkustofnun", chapter: undefined, article: 9, status: "OK" },
  { nr: "100/2024", name: "Lög um skák", chapter: 3, article: 9, status: "OK" },
  { nr: "90/2024", name: "Lög um Nýsköpunarsjóðinn Krít", chapter: 1, article: 16, status: "OK" },
  { nr: "5/2025", name: "Forsetaúrskurður um skiptigu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands", chapter: 13, status: "OK" },
  { nr: "4/2025", name: "Forsetaúrskurður um skiptigu Stjórnarráðs Íslands í ráðuneyti", chapter: 0, status: "OK" },
  { nr: "130/2024", name: "Lög um stuðningsáætli til rekstraraðila í Grindavíkurbæ vegna jarðhræringa á Reykjanesskkaga", chapter: 17, status: "OK" },
  { nr: "126/2024", name: "Lög um heimild fyrir ríkisstjórnina til að samþykkja hækkun á kvóta Íslands hjá Alþjóðagjaldeyrissjóðnum", chapter: 2, status: "OK" },
  { nr: "111/2024", name: "Lög um Náttúruverndarstoufun", chapter: 1, article: 6, status: "OK" },
  { nr: "110/2024", name: "Lög um Umhverfis- og orkustofnun", chapter: undefined, article: 9, status: "OK" },
  { nr: "100/2024", name: "Lög um skák", chapter: 3, article: 9, status: "OK" },
  { nr: "90/2024", name: "Lög um Nýsköpunarsjóðinn Krít", chapter: 1, article: 16, status: "OK" },
  { nr: "5/2025", name: "Forsetaúrskurður um skiptigu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands", chapter: 13, status: "OK" },
  { nr: "4/2025", name: "Forsetaúrskurður um skiptigu Stjórnarráðs Íslands í ráðuneyti", chapter: 0, status: "OK" },
  { nr: "130/2024", name: "Lög um stuðningsáætli til rekstraraðila í Grindavíkurbæ vegna jarðhræringa á Reykjanesskkaga", chapter: 17, status: "OK" },
  { nr: "126/2024", name: "Lög um heimild fyrir ríkisstjórnina til að samþykkja hækkun á kvóta Íslands hjá Alþjóðagjaldeyrissjóðnum", chapter: 2, status: "OK" },
  { nr: "111/2024", name: "Lög um Náttúruverndarstoufun", chapter: 1, article: 6, status: "OK" },
  { nr: "110/2024", name: "Lög um Umhverfis- og orkustofnun", chapter: undefined, article: 9, status: "OK" },
  { nr: "100/2024", name: "Lög um skák", chapter: 3, article: 9, status: "OK" },
  { nr: "90/2024", name: "Lög um Nýsköpunarsjóðinn Krít", chapter: 1, article: 16, status: "OK" },
  { nr: "5/2025", name: "Forsetaúrskurður um skiptigu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands", chapter: 13, status: "OK" },
  { nr: "4/2025", name: "Forsetaúrskurður um skiptigu Stjórnarráðs Íslands í ráðuneyti", chapter: 0, status: "OK" },
  { nr: "130/2024", name: "Lög um stuðningsáætli til rekstraraðila í Grindavíkurbæ vegna jarðhræringa á Reykjanesskkaga", chapter: 17, status: "OK" },
  { nr: "126/2024", name: "Lög um heimild fyrir ríkisstjórnina til að samþykkja hækkun á kvóta Íslands hjá Alþjóðagjaldeyrissjóðnum", chapter: 2, status: "OK" },
  { nr: "111/2024", name: "Lög um Náttúruverndarstoufun", chapter: 1, article: 6, status: "OK" },
  { nr: "110/2024", name: "Lög um Umhverfis- og orkustofnun", chapter: undefined, article: 9, status: "OK" },
  { nr: "100/2024", name: "Lög um skák", chapter: 3, article: 9, status: "OK" },
  { nr: "90/2024", name: "Lög um Nýsköpunarsjóðinn Krít", chapter: 1, article: 16, status: "OK" },
  { nr: "5/2025", name: "Forsetaúrskurður um skiptigu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands", chapter: 13, status: "OK" },
  { nr: "4/2025", name: "Forsetaúrskurður um skiptigu Stjórnarráðs Íslands í ráðuneyti", chapter: 0, status: "OK" },
  { nr: "130/2024", name: "Lög um stuðningsáætli til rekstraraðila í Grindavíkurbæ vegna jarðhræringa á Reykjanesskkaga", chapter: 17, status: "OK" },
  { nr: "126/2024", name: "Lög um heimild fyrir ríkisstjórnina til að samþykkja hækkun á kvóta Íslands hjá Alþjóðagjaldeyrissjóðnum", chapter: 2, status: "OK" },
  { nr: "111/2024", name: "Lög um Náttúruverndarstoufun", chapter: 1, article: 6, status: "OK" },
  { nr: "110/2024", name: "Lög um Umhverfis- og orkustofnun", chapter: undefined, article: 9, status: "OK" },
  { nr: "100/2024", name: "Lög um skák", chapter: 3, article: 9, status: "OK" },
  { nr: "90/2024", name: "Lög um Nýsköpunarsjóðinn Krít", chapter: 1, article: 16, status: "OK" },
  { nr: "5/2025", name: "Forsetaúrskurður um skiptigu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands", chapter: 13, status: "OK" },
  { nr: "4/2025", name: "Forsetaúrskurður um skiptigu Stjórnarráðs Íslands í ráðuneyti", chapter: 0, status: "OK" },
  { nr: "130/2024", name: "Lög um stuðningsáætli til rekstraraðila í Grindavíkurbæ vegna jarðhræringa á Reykjanesskkaga", chapter: 17, status: "OK" },
  { nr: "126/2024", name: "Lög um heimild fyrir ríkisstjórnina til að samþykkja hækkun á kvóta Íslands hjá Alþjóðagjaldeyrissjóðnum", chapter: 2, status: "OK" },
  { nr: "111/2024", name: "Lög um Náttúruverndarstoufun", chapter: 1, article: 6, status: "OK" },
  { nr: "110/2024", name: "Lög um Umhverfis- og orkustofnun", chapter: undefined, article: 9, status: "OK" },
  { nr: "100/2024", name: "Lög um skák", chapter: 3, article: 9, status: "OK" },
  { nr: "90/2024", name: "Lög um Nýsköpunarsjóðinn Krít", chapter: 1, article: 16, status: "OK" },
  { nr: "5/2025", name: "Forsetaúrskurður um skiptigu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands", chapter: 13, status: "OK" },
  { nr: "4/2025", name: "Forsetaúrskurður um skiptigu Stjórnarráðs Íslands í ráðuneyti", chapter: 0, status: "OK" },
  { nr: "130/2024", name: "Lög um stuðningsáætli til rekstraraðila í Grindavíkurbæ vegna jarðhræringa á Reykjanesskkaga", chapter: 17, status: "OK" },
  { nr: "126/2024", name: "Lög um heimild fyrir ríkisstjórnina til að samþykkja hækkun á kvóta Íslands hjá Alþjóðagjaldeyrissjóðnum", chapter: 2, status: "OK" },
  { nr: "111/2024", name: "Lög um Náttúruverndarstoufun", chapter: 1, article: 6, status: "OK" },
  { nr: "110/2024", name: "Lög um Umhverfis- og orkustofnun", chapter: undefined, article: 9, status: "OK" },
  { nr: "100/2024", name: "Lög um skák", chapter: 3, article: 9, status: "OK" },
  { nr: "90/2024", name: "Lög um Nýsköpunarsjóðinn Krít", chapter: 1, article: 16, status: "OK" },
  { nr: "88/2024", name: "Lög um Mannréttindastofnun Íslands", chapter: 1, article: 17, status: "OK" }
];

export default function Home() {
  const [searchQuery, setSearchQuery] = createSignal("");
  
  // TODO: return type should come from the API
  const [laws] = createResource<Law[]>(LawService.listLaws);
  const [stats] = createResource(async () => ({
    totalCount: 1699,
    emptyCount: 915,
    nonEmptyCount: 784
  }));

  // Filter laws by search query on each key press
  const filteredLaws = createMemo(() => {
    const query = searchQuery().toLowerCase().trim();
    const all = laws() ?? [];
    
    if (!query) return all;

    return all.filter((law) => {
      const nrMatch = law.nr.toLowerCase().includes(query);
      const nameMatch = law.name.toLowerCase().includes(query);
      return nrMatch || nameMatch;
    });
  });

  return (
    <div>
      <Header 
        showSearch={true}
        searchValue={searchQuery()}
        onSearchChange={setSearchQuery}
      />

      <div class="container mx-auto px-4">
        <LawStats
          totalCount={stats()?.totalCount ?? 0}
          emptyCount={stats()?.emptyCount ?? 0}
          nonEmptyCount={stats()?.nonEmptyCount ?? 0}
        />
        <LawTable laws={filteredLaws()} />
      </div>
    </div>
  );
}
