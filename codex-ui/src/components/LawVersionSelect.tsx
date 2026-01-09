import { For, createMemo, createEffect } from 'solid-js';

interface LawVersionSelectProps {
    value: string;
    onInput: (value: string) => void;
    versions: string[];
    disabled?: boolean;
}

export default function LawVersionSelect(props: LawVersionSelectProps) {
    let selectRef: HTMLSelectElement | undefined;

    // Sort versions in reverse order
    const sortedVersions = createMemo(() => {
        return [...props.versions].sort().reverse();
    });

    // Sync the select value when versions become available
    // This ensures the correct option is selected when options are added after initial render
    createEffect(() => {
        const versions = sortedVersions();
        const currentValue = props.value;

        // When versions load and include the current value, ensure select shows it
        if (selectRef && currentValue && versions.length > 0 && versions.includes(currentValue)) {
            // Only update if the select value doesn't match
            if (selectRef.value !== currentValue) {
                selectRef.value = currentValue;
            }
        }
    });

    return (
        <select
            ref={selectRef}
            value={props.value}
            onInput={(e) => {
                const value = e.currentTarget.value;
                props.onInput(value);
            }}
            disabled={props.disabled}
            class="px-3 py-1 bg-white/10 text-white border border-white/20 rounded disabled:opacity-50 disabled:cursor-not-allowed"
        >
            <For each={sortedVersions()}>
                {version => (
                    <option value={version} class="bg-gray-800 text-white">
                        {version}
                    </option>
                )}
            </For>
        </select>
    );
}
