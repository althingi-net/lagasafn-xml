/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Advert } from '../models/Advert';
import type { AdvertIndex } from '../models/AdvertIndex';
import type { AdvertIntentDetails } from '../models/AdvertIntentDetails';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdvertService {
    /**
     * Returns a list of all adverts.
     * @param codexVersion
     * @returns AdvertIndex OK
     * @throws ApiError
     */
    public static listAdverts(
        codexVersion?: string,
    ): CancelablePromise<AdvertIndex> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/advert/list',
            query: {
                'codex_version': codexVersion,
            },
        });
    }
    /**
     * Returns a single requested advert.
     * @param identifier
     * @returns Advert OK
     * @throws ApiError
     */
    public static getAdvert(
        identifier: string,
    ): CancelablePromise<Advert> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/advert/get',
            query: {
                'identifier': identifier,
            },
        });
    }
    /**
     * Returns intent details with comparisons.
     * @param identifier
     * @returns AdvertIntentDetails OK
     * @throws ApiError
     */
    public static getAdvertIntents(
        identifier: string,
    ): CancelablePromise<AdvertIntentDetails> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/advert/intents',
            query: {
                'identifier': identifier,
            },
        });
    }
}
