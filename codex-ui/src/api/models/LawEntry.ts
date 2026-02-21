/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Intermediary model for a legal entry in the index.
 */
export type LawEntry = {
    identifier: string;
    name: string;
    codex_version: string;
    chapter_count: number;
    art_count: number;
    problems: Record<string, any>;
    versions: Array<string>;
    nr: number;
    year: number;
};

