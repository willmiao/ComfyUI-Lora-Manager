import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js'
import { resolve } from 'path'

export default defineConfig({
    plugins: [
        vue(),
        cssInjectedByJsPlugin()  // Inject CSS into JS for ComfyUI compatibility
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
            external: [
                '../../../scripts/app.js',
                '../loras_widget.js'
            ],
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
