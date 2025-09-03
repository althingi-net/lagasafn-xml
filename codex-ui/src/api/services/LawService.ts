/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LawIndex } from '../models/LawIndex';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class LawService {
    /**
     * Search legal codex by content.
     * Returns search-specific results explaining what was found given a provided
     * content query.
     * @param q
     * @returns any OK
     * @throws ApiError
     */
    public static search(
        q: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/law/search/',
            query: {
                'q': q,
            },
        });
    }
    /**
     * Parse human-readable legal reference.
     * Parse a human-readable legal reference and return path and content
     * information.
     * @param reference
     * @returns any OK
     * @throws ApiError
     */
    public static parseReferenceString(
        reference: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/law/parse-reference/',
            query: {
                'reference': reference,
            },
        });
    }
    /**
     * Get segment from a law in the legal codex.
     * Takes identity information (nr/year) and an XPath string, and returns the
     * XML content found in the corresponding legal codex."
     * @param lawNr
     * @param lawYear
     * @param xpath
     * @returns any OK
     * @throws ApiError
     */
    public static getSegment(
        lawNr: string,
        lawYear: number,
        xpath: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/law/get-segment/',
            query: {
                'law_nr': lawNr,
                'law_year': lawYear,
                'xpath': xpath,
            },
        });
    }
    /**
     * Normalize a law XML document.
     * Takes an uploaded XML law and makes sure that it is formatted in the same
     * way as the codex. Useful for comparison.
     * @param formData
     * @returns any OK
     * @throws ApiError
     */
    public static normalize(
        formData: {
            input_file: Blob;
        },
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/law/normalize/',
            formData: formData,
            mediaType: 'multipart/form-data',
        });
    }
    /**
     * Returns a list of all laws.
     * @returns LawIndex OK
     * @throws ApiError
     */
    public static listLaws(): CancelablePromise<LawIndex> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/law/list',
        });
    }
}
