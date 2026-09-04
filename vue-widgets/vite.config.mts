import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js'
import { dirname, resolve } from 'path'

// Specifiers that must stay external. The bundle is emitted to
// web/comfyui/vue-widgets/, and ComfyUI serves that directory's parent
// (web/comfyui) at /extensions/ComfyUI-Lora-Manager/, so one "../" from the
// bundle reaches web/comfyui modules and three "../../.." reach ComfyUI's
// own runtime scripts at runtime.
//
// scripts/app.js and scripts/api.js are intentionally NOT listed here: they
// are externalized by the keep-runtime-modules-external plugin below, which
// also rewrites the shallower "../../scripts/*" specifiers used by modules
// inlined from web/comfyui/ so every binding dedupes into a single import.
const EXTERNAL_SPECIFIERS = [
    '../loras_widget.js',
    '../autocomplete.js',
    '../preview_tooltip.js'
]

export default defineConfig({
    plugins: [
        vue(),
        cssInjectedByJsPlugin(),  // Inject CSS into JS for ComfyUI compatibility
        // Keep shared runtime modules external instead of inlining them into
        // the bundle. This guards against the inlined-shim bug class (the
        // removed active-filters chip ended up writing settings to a dead
        // in-memory store this way):
        //
        // 1. Modules under web/comfyui/ import the repo-root scripts/app.js
        //    TEST SHIM as "../../scripts/app.js" — a depth that resolves to
        //    the shim on the build filesystem but 404s at the bundle's
        //    runtime location. Rewrite to the canonical bundle-depth
        //    specifier so every app/api binding in the bundle is the REAL
        //    ComfyUI module.
        // 2. web/comfyui/settings.js must never be duplicated into the
        //    bundle: it registers settings via a module-level side effect
        //    and owns module state. Externalize it to "../settings.js" so
        //    the bundle binds to the SAME vanilla module instance that the
        //    ComfyUI extension loader already loaded.
        {
            name: 'lora-manager:keep-runtime-modules-external',
            enforce: 'pre',
            resolveId(source, importer) {
                const scriptsMatch = source.match(/^(\.\.\/)+scripts\/(app|api)\.js$/)
                if (scriptsMatch) {
                    return { id: `../../../scripts/${scriptsMatch[2]}.js`, external: true }
                }
                if (
                    importer &&
                    /[\\/]web[\\/]comfyui[\\/]settings\.js$/.test(
                        resolve(dirname(importer), source)
                    )
                ) {
                    return { id: '../settings.js', external: true }
                }
                return null
            },
        },
        // Warning twin of the rewrite above: importing web/comfyui/* from
        // widget source inlines that module into the bundle, duplicating any
        // module-level side effects/state it owns. The settings.js and
        // scripts/app|api.js imports are made safe by the plugin above, but
        // review any further such import deliberately.
        {
            name: 'lora-manager:warn-web-comfyui-imports',
            enforce: 'pre',
            resolveId(source, importer) {
                if (
                    importer &&
                    /[\\/]vue-widgets[\\/]src[\\/]/.test(importer) &&
                    /[\\/]web[\\/]comfyui[\\/]/.test(source)
                ) {
                    this.warn(
                        `[vue-widgets] Inlining web/comfyui module "${source}" into the bundle. ` +
                        'settings.js and scripts/app|api.js imports are externalized by this config, ' +
                        'but the inlined copy still duplicates module-level side effects — verify that is intended.'
                    )
                }
                return null
            },
        },
    ],
    resolve: {
        alias: {
            '@': resolve(__dirname, './src')
        }
    },
    build: {
        lib: {
            entry: resolve(__dirname, './src/main.ts'),
            formats: ['es'],
            fileName: 'lora-manager-widgets'
        },
        rollupOptions: {
            external: EXTERNAL_SPECIFIERS,
            output: {
                dir: '../web/comfyui/vue-widgets',
                entryFileNames: 'lora-manager-widgets.js',
                chunkFileNames: 'assets/[name]-[hash].js',
                assetFileNames: 'assets/[name]-[hash][extname]'
            }
        },
        sourcemap: true,
        minify: false
    },
    define: {
        'process.env.NODE_ENV': JSON.stringify('production')
    }
})

