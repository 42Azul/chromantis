package org.chromantis.android

import androidx.compose.ui.InternalComposeUiApi
import androidx.compose.ui.platform.WindowRecomposerFactory
import androidx.compose.ui.platform.WindowRecomposerPolicy

// The HTTPS fixtures use real IO. Keep window effects and layout on Android's UI thread.
@OptIn(InternalComposeUiApi::class)
internal fun withAndroidWindowRecomposer(block: () -> Unit) {
    WindowRecomposerPolicy.withFactory(WindowRecomposerFactory.LifecycleAware, block)
}
