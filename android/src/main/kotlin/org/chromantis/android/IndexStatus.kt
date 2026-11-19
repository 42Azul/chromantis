package org.chromantis.android

import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import org.json.JSONObject

internal enum class IndexState {
    NOT_STARTED,
    RUNNING,
    SUCCEEDED,
    FAILED,
    UNKNOWN,
}

internal data class IndexStatus(val state: IndexState, val indexedAt: String?)

internal fun indexStatus(response: JSONObject): IndexStatus {
    val item = response.getJSONObject("item")
    val state =
        when (if (item.isNull("sync_status")) null else item.getString("sync_status")) {
            null -> IndexState.NOT_STARTED
            "running" -> IndexState.RUNNING
            "succeeded" -> IndexState.SUCCEEDED
            "failed" -> IndexState.FAILED
            else -> IndexState.UNKNOWN
        }
    return IndexStatus(state, if (item.isNull("indexed_at")) null else item.getString("indexed_at"))
}

@Composable
internal fun IndexStatusScreen(api: ChromantisApi, onExpired: () -> Unit) {
    var revision by remember { mutableIntStateOf(0) }
    Text(stringResource(R.string.index_explanation))
    key(revision) {
        LoadContent(onExpired, load = { api.indexStatus() }) { status ->
            val label =
                when (status.state) {
                    IndexState.NOT_STARTED -> R.string.index_not_started
                    IndexState.RUNNING -> R.string.index_running
                    IndexState.SUCCEEDED -> R.string.index_succeeded
                    IndexState.FAILED -> R.string.index_failed
                    IndexState.UNKNOWN -> R.string.index_unknown
                }
            Text(stringResource(label))
            Text(
                status.indexedAt?.let { stringResource(R.string.index_last_success, indexDate(it)) }
                    ?: stringResource(R.string.index_no_success)
            )
            TextButton(onClick = { revision++ }) { Text(stringResource(R.string.index_refresh)) }
        }
    }
}

internal fun indexDate(value: String): String =
    runCatching {
            OffsetDateTime.parse(value)
                .atZoneSameInstant(ZoneId.systemDefault())
                .format(
                    DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT)
                )
        }
        .getOrDefault(value)
