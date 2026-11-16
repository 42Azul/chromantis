package org.chromantis.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class PhotoTagEditTest {
    @Test
    fun batchEditsSendOnlySelectedIdentitiesAndExplicitAdditions() {
        val photos =
            listOf(
                TaggedPhoto("trip/first.jpg", "first-id", setOf(8), setOf("beach")),
                TaggedPhoto("trip/third.jpg", "third-id", emptySet(), emptySet()),
            )
        val edit = photoTagEdit(photos, person = 7, tag = " picnic ", remove = false)
        val selected = edit.getJSONArray("photos")
        assertEquals(2, selected.length())
        assertEquals("trip/first.jpg", selected.getJSONObject(0).getString("path"))
        assertEquals("third-id", selected.getJSONObject(1).getString("identity"))
        assertEquals(
            setOf("path", "identity"),
            selected.getJSONObject(0).keys().asSequence().toSet(),
        )
        assertEquals(7L, edit.getJSONArray("add_people").getLong(0))
        assertEquals("picnic", edit.getJSONArray("manual_add").getString(0))
        assertFalse(edit.has("remove_people"))
    }

    @Test
    fun existingPhotoAnnotationCanBeRemovedByIdentityWithoutReplacingOtherTags() {
        val photo =
            taggedPhoto(
                JSONObject(
                    """{"path":"trip/first.jpg","identity":"first-id","people":[{"person_id":7,"origin":"manual"}],"manual_tags":[{"tag":"picnic","origin":"manual"}]}"""
                )
            )
        assertEquals(setOf(7L), photo.people)
        assertEquals(setOf("picnic"), photo.tags)
        val edit = photoTagEdit(listOf(photo), person = 7, tag = "", remove = true)
        assertEquals(7L, edit.getJSONArray("remove_people").getLong(0))
        assertFalse(edit.has("add_people"))
        assertFalse(edit.has("manual_remove"))
    }
}
