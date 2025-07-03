import { useParams } from "@solidjs/router";
import Header from "~/components/Header";

interface Law {
  nr: string;
  name: string;
  chapter?: number;
  article?: number;
  status: 'OK' | string;
  content?: string; // Mock content
}

// Mock data for individual law view
const MOCK_LAW_CONTENT = `# Lög um skák

## 1. gr. Markmið
Markmið laga þessara er að efla skákíþróttina á Íslandi og tryggja að hún geti dafnað og þróast.

## 2. gr. Gildissvið
Lög þessi gilda um skipulag og starfsemi skákhreyfingar á Íslandi.

## 3. gr. Skáksamband Íslands
Skáksamband Íslands er æðsti aðili skákmála á Íslandi.`;

export default function LawView() {
  const params = useParams();
  
  // In a real app, this would fetch from an API
  const law: Law = {
    nr: `${params.number}/${params.year}`,
    name: "Lög um skák",
    chapter: 3,
    article: 9,
    status: "OK",
    content: MOCK_LAW_CONTENT
  };

  return (
    <div>
      <Header showSearch={false} />
      
      <div class="container mx-auto px-4 py-8">
        <div class="bg-white rounded-lg shadow-sm p-6">
          <div class="mb-6">
            <h1 class="text-3xl font-semibold mb-2">{law.name}</h1>
            <p class="text-gray-600">Nr. {law.nr}</p>
          </div>

          <div class="prose max-w-none">
            <pre class="whitespace-pre-wrap font-sans">{law.content}</pre>
          </div>
        </div>
      </div>
    </div>
  );
} 