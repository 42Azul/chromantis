package org.chromantis.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class IndexStatusTest {
    @Test
    fun neverScannedAndOlderResponsesDoNotInventASuccess() {
        for (item in listOf("{}", """{"sync_status":null,"indexed_at":null}""")) {
            val status = indexStatus(JSONObject().put("item", JSONObject(item)))
            assertEquals(IndexState.NOT_STARTED, status.state)
            assertNull(status.indexedAt)
        }
    }

    @Test
    fun runningOrFailedScanKeepsTheLastSuccessfulIndexDate() {
        for ((value, expected) in
            listOf(
                "running" to IndexState.RUNNING,
                "failed" to IndexState.FAILED,
                "succeeded" to IndexState.SUCCEEDED,
            )) {
            val status =
                indexStatus(
                    JSONObject(
                        """{"item":{"sync_status":"$value","indexed_at":"2026-11-18T17:00:00+00:00"}}"""
                    )
                )
            assertEquals(expected, status.state)
            assertEquals("2026-11-18T17:00:00+00:00", status.indexedAt)
        }
    }

    @Test
    fun unknownServerStateIsNotReportedAsSuccessful() {
        assertEquals(
            IndexState.UNKNOWN,
            indexStatus(JSONObject("""{"item":{"sync_status":"future-state"}}""")).state,
        )
    }
}
