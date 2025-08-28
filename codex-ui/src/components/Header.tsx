import { JSX } from 'solid-js';

interface HeaderProps {
    showSearch?: boolean;
    onSearchChange?: (value: string) => void;
    searchValue?: string;
}

export default function Header(props: HeaderProps) {
    return (
        <>
            <div class="fixed top-0 left-0 right-0 bg-black text-white w-full z-10">
                <div class="container mx-auto px-4 py-4 flex items-center">
                    <div class="flex items-center gap-8">
                        <h1 class="text-xl font-medium">
                            <a href="/" class="hover:text-gray-300">Legal Codex (30. apríl 2025)</a>
                        </h1>
                        <a href="/" class="text-base text-gray-300 hover:text-white">Content Search</a>
                    </div>
                    {props.showSearch && (
                        <div class="ml-auto w-64">
                            <input
                                type="text"
                                placeholder="Leita"
                                class="w-full px-3 py-1.5 rounded bg-white/90 text-black placeholder-gray-500"
                                value={props.searchValue}
                                onInput={e => props.onSearchChange?.(e.currentTarget.value)}
                            />
                        </div>
                    )}
                </div>
            </div>
            {/* Spacer to prevent content from going under header */}
            <div class="h-[60px]" />
        </>
    );
}
