/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Chapter } from './Chapter';
export type Law = {
    identifier: string;
    name: string;
    codex_version: string;
    chapter_count: number;
    art_count: number;
    problems: Record<string, any>;
    nr: number;
    year: number;
    chapters: Array<Chapter>;
    versions: Array<string>;
    html_text: string;
};

