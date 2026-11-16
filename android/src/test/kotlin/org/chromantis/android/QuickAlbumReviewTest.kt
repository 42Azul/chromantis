package org.chromantis.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class QuickAlbumReviewTest {
    @Test
    fun reviewActsOnlyAtTheThresholdInTheReleasedDirection() {
        assertNull(reviewGesture(71f, 72f, canAccept = true))
        assertNull(reviewGesture(-71f, 72f, canAccept = true))
        assertEquals(ReviewGesture.ACCEPT, reviewGesture(72f, 72f, canAccept = true))
        assertEquals(ReviewGesture.SKIP, reviewGesture(-72f, 72f, canAccept = true))
    }

    @Test
    fun albumsWithoutASuggestionCanOnlyBeSkipped() {
        assertNull(reviewGesture(100f, 72f, canAccept = false))
        assertEquals(ReviewGesture.SKIP, reviewGesture(-100f, 72f, canAccept = false))
    }
}
