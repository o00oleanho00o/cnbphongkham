package com.example.pema_native_template

import android.content.Intent
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var camera: PemaCamera? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        camera = PemaCamera(this).also {
            MethodChannel(flutterEngine.dartExecutor.binaryMessenger, PemaCamera.CHANNEL)
                .setMethodCallHandler(it)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        camera?.restoreState(savedInstanceState)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        camera?.saveState(outState)
    }

    @Deprecated("FlutterActivity is not a ComponentActivity, so the result API is unavailable")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (camera?.onActivityResult(requestCode, resultCode) != true) {
            super.onActivityResult(requestCode, resultCode, data)
        }
    }

    override fun onDestroy() {
        camera?.dispose()
        camera = null
        super.onDestroy()
    }
}
