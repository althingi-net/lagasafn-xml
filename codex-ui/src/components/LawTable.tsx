import { For } from 'solid-js';
import { A } from '@solidjs/router';
import { LawEntry } from '~/api';

interface LawTableProps {
    laws: LawEntry[];
}

export default function LawTable(props: LawTableProps) {
    const getLawUrl = (nr: string) => {
        const [number, year] = nr.split('/');
        return `/law/${number}/${year}`;
    };

    return (
        <div class="overflow-x-auto">
            <table class="w-full">
                <thead>
                    <tr class="border-b">
                        <th class="text-left py-2 px-4">Nr.</th>
                        <th class="text-left py-2 px-4">Name</th>
                        <th class="text-right py-2 px-4">Ch.</th>
                        <th class="text-right py-2 px-4">Art.</th>
                        <th class="text-center py-2 px-4">Status</th>
                    </tr>
                </thead>
                <tbody>
                    <For each={props.laws}>
                        {law => (
                            <tr class="border-b hover:bg-gray-50/50">
                                <td class="py-2 px-4">
                                    <A
                                        href={getLawUrl(law.nr?.toString() ?? '')}
                                        class="text-blue-600 hover:text-blue-800"
                                    >
                                        {law.identifier}
                                    </A>
                                </td>
                                <td class="py-2 px-4">
                                    <A
                                        href={getLawUrl(law.nr?.toString() ?? '')}
                                        class="hover:text-blue-600"
                                    >
                                        {law.name}
                                    </A>
                                </td>
                                <td class="py-2 px-4 text-right">{law.chapter_count}</td>
                                <td class="py-2 px-4 text-right">{law.art_count}</td>
                                <td class="py-2 px-4 text-center">
                                    <span class={`px-2 py-1 rounded ${getSuccess(law) ? 'bg-green-500 text-white' : ''}`}>
                                        OK
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

const getSuccess = (law: LawEntry) => {
    const success = law.problems?.content as { success: boolean };
    return success.success;
};
