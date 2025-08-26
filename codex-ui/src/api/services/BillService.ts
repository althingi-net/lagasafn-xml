/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class BillService {
    /**
     * Bill Meta
     * Publish bill meta XML data as POST body.
     *
     * Example: curl -H 'Content-Type: application/xml'  -X POST http://127.0.0.1:9000/api/bill/meta --data '<bill><lagasafnId>1</lagasafnId><title>Skógræktarlög</title><description>Frumvarp um eflingu skógræktar á Íslandi</description></bill>'
     * @returns any OK
     * @throws ApiError
     */
    public static billApiBillMeta(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/bill/meta',
        });
    }
    /**
     * Bill Validate
     * Validate bill XML provided as POST body.
     *
     * Example: curl -H 'Content-Type: application/xml'  -X POST http://10.110.0.2:9000/api/bill/document/validate --data '<bill><title>test</title><law nr="5" year="1995">test</law></bill>'
     * @returns any OK
     * @throws ApiError
     */
    public static billApiBillValidate(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/bill/document/validate',
        });
    }
    /**
     * Bill Publish
     * Publish bill XML provided as POST body.
     *
     * Example: curl -H 'Content-Type: application/xml'  -X POST http://127.0.0.1:9000/api/bill/document/publish --data '<bill><title>test</title><law nr="5" year="1995">test</law></bill>'
     * @param billId
     * @returns any OK
     * @throws ApiError
     */
    public static billApiBillPublish(
        billId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/bill/{bill_id}/document/publish',
            path: {
                'bill_id': billId,
            },
        });
    }
}
