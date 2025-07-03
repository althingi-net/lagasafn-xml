import { For } from "solid-js";

interface Law {
  nr: string;
  name: string;
  chapter?: number;
  article?: number;
  status: 'OK' | string;
}

interface LawTableProps {
  laws: Law[];
}

export default function LawTable(props: LawTableProps) {
  return (
    <div class="overflow-x-auto">
      <table class="w-full">
        <thead>
          <tr class="border-b">
            <th class="text-left py-2">Nr.</th>
            <th class="text-left py-2">Name</th>
            <th class="text-right py-2">Ch.</th>
            <th class="text-right py-2">Art.</th>
            <th class="text-center py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          <For each={props.laws}>
            {(law) => (
              <tr class="border-b hover:bg-gray-50/50">
                <td class="py-2 text-blue-600">{law.nr}</td>
                <td class="py-2">{law.name}</td>
                <td class="py-2 text-right">{law.chapter}</td>
                <td class="py-2 text-right">{law.article}</td>
                <td class="py-2 text-center">
                  <span class={`px-2 py-1 rounded ${law.status === 'OK' ? 'bg-green-500 text-white' : ''}`}>
                    {law.status}
                  </span>
                </td>
              </tr>
            )}
          </For>
        </tbody>
      </table>
    </div>
  );
} 