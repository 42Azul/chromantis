package org.chromantis.android

import org.junit.Assert.assertEquals
import org.junit.Test

class PhotoSwipeReviewTest {
    @Test
    fun commitsOnlyAcceptedPhotosWithNewLinks() {
        val first = TaggedPhoto("first", "first-id", emptySet(), emptySet())
        val second = TaggedPhoto("second", "second-id", emptySet(), emptySet())
        val third = TaggedPhoto("third", "third-id", setOf(7), emptySet())
        val fourth = TaggedPhoto("fourth", "fourth-id", emptySet(), emptySet())
        val photos = listOf(first, second, third, fourth)
        val decisions = listOf(ReviewGesture.ACCEPT, ReviewGesture.SKIP, ReviewGesture.ACCEPT)

        assertEquals(listOf(first), photoReviewTargets(photos, decisions, 7))
        assertEquals(listOf(first, third), photoReviewTargets(photos, decisions, 8))
    }

    @Test
    fun undoAndSkipLeaveAnAcceptedPhotoOutOfTheWrite() {
        val photos =
            listOf(
                TaggedPhoto("first", "first-id", emptySet(), emptySet()),
                TaggedPhoto("second", "second-id", emptySet(), emptySet()),
            )
        val decisions = listOf(ReviewGesture.SKIP, ReviewGesture.ACCEPT)
        assertEquals(listOf(photos[1]), photoReviewTargets(photos, decisions, 7))
        assertEquals(emptyList<TaggedPhoto>(), photoReviewTargets(photos, decisions.dropLast(1), 7))
        assertEquals(emptyList<TaggedPhoto>(), photoReviewTargets(photos, emptyList(), 7))
    }
}
