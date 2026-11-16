package org.chromantis.android

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp

internal enum class Appearance(@get:StringRes val label: Int) {
    SYSTEM(R.string.theme_system),
    LIGHT(R.string.theme_light),
    DARK(R.string.theme_dark);

    fun isDark(systemDark: Boolean): Boolean = this == DARK || (this == SYSTEM && systemDark)

    companion object {
        fun fromPreference(value: String?): Appearance = entries.find { it.name == value } ?: SYSTEM
    }
}

internal val lightPalette =
    lightColorScheme(
        primary = Color(0xff285847),
        onPrimary = Color.White,
        primaryContainer = Color(0xffd0e9db),
        onPrimaryContainer = Color(0xff153d30),
        surface = Color(0xfff9faf7),
        onSurface = Color(0xff19211d),
        surfaceContainer = Color(0xffeef1ed),
        surfaceContainerHigh = Color(0xffe7ede7),
        surfaceContainerHighest = Color(0xffe0e7e0),
        surfaceVariant = Color(0xffe4ebe5),
        onSurfaceVariant = Color(0xff46554d),
    )

internal val darkPalette =
    darkColorScheme(
        primary = Color(0xffa5d4bf),
        onPrimary = Color(0xff10372a),
        primaryContainer = Color(0xff29493e),
        onPrimaryContainer = Color(0xffd7f2e4),
        surface = Color(0xff151a18),
        onSurface = Color(0xffe6ece7),
        surfaceContainer = Color(0xff202923),
        surfaceContainerHigh = Color(0xff28322b),
        surfaceContainerHighest = Color(0xff303b34),
        surfaceVariant = Color(0xff303b34),
        onSurfaceVariant = Color(0xffc2cdc5),
    )

@Composable
internal fun SettingsDialog(
    appearance: Appearance,
    onAppearance: (Appearance) -> Unit,
    onClose: () -> Unit,
    onSignOut: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(stringResource(R.string.appearance)) },
        text = {
            Column(Modifier.selectableGroup()) {
                Appearance.entries.forEach { mode ->
                    Row(
                        Modifier.fillMaxWidth()
                            .selectable(
                                selected = appearance == mode,
                                onClick = { onAppearance(mode) },
                                role = Role.RadioButton,
                            )
                            .padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = appearance == mode, onClick = null)
                        Text(stringResource(mode.label), Modifier.padding(start = 12.dp))
                    }
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onSignOut) { Text(stringResource(R.string.sign_out)) }
        },
        confirmButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.done)) } },
    )
}
