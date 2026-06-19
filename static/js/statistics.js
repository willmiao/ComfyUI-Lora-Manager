// Statistics page functionality
import { appCore } from './core.js';
import { showToast } from './utils/uiHelpers.js';
import { translate } from './utils/i18nHelpers.js';
import { i18n } from './i18n/index.js';

// Chart.js import (assuming it's available globally or via CDN)
// If Chart.js isn't available, we'll need to add it to the project

export class StatisticsManager {
    constructor() {
        this.charts = {};
        this.data = {};
        this.initialized = false;
        this.listStates = {
            lora: { offset: 0, limit: 50, sort: 'desc', isLoading: false, hasMore: true },
            checkpoint: { offset: 0, limit: 50, sort: 'desc', isLoading: false, hasMore: true },
            embedding: { offset: 0, limit: 50, sort: 'desc', isLoading: false, hasMore: true }
        };
    }

    async initialize() {
        if (this.initialized) return;

        console.log('StatisticsManager: Initializing...');
        
        // Initialize tab functionality
        this.initializeTabs();
        
        // Load initial data
        await this.loadAllData();
        
        // Initialize charts and visualizations
        await this.initializeVisualizations();
        
        this.initialized = true;
    }

    initializeTabs() {
        const tabButtons = document.querySelectorAll('.tab-button');
        const tabPanels = document.querySelectorAll('.tab-panel');

        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tabId = button.dataset.tab;
                
                // Update active tab button
                tabButtons.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');
                
                // Update active tab panel
                tabPanels.forEach(panel => panel.classList.remove('active'));
                const targetPanel = document.getElementById(`${tabId}-panel`);
                if (targetPanel) {
                    targetPanel.classList.add('active');
                    
                    // Refresh charts when tab becomes visible
                    this.refreshChartsInPanel(tabId);
                }
            });
        });
    }

    async loadAllData() {
        try {
            // Load all statistics data in parallel
            const [
                collectionOverview,
                usageAnalytics,
                baseModelDistribution,
                tagAnalytics,
                storageAnalytics,
                insights
            ] = await Promise.all([
                this.fetchData('/api/lm/stats/collection-overview'),
                this.fetchData('/api/lm/stats/usage-analytics'),
                this.fetchData('/api/lm/stats/base-model-distribution'),
                this.fetchData('/api/lm/stats/tag-analytics'),
                this.fetchData('/api/lm/stats/storage-analytics'),
                this.fetchData('/api/lm/stats/insights')
            ]);

            this.data = {
                collection: collectionOverview.data,
                usage: usageAnalytics.data,
                baseModels: baseModelDistribution.data,
                tags: tagAnalytics.data,
                storage: storageAnalytics.data,
                insights: insights.data
            };

            console.log('Statistics data loaded:', this.data);
        } catch (error) {
            console.error('Error loading statistics data:', error);
            showToast('toast.general.statisticsLoadFailed', {}, 'error');
        }
    }

    async fetchData(endpoint) {
        const response = await fetch(endpoint);
        if (!response.ok) {
            throw new Error(`Failed to fetch ${endpoint}: ${response.statusText}`);
        }
        return response.json();
    }

    async initializeVisualizations() {
        // Initialize metrics cards
        this.renderMetricsCards();
        
        // Initialize charts
        this.initializeCharts();
        
        // Initialize lists and other components
        await this.initializeLists();
        this.renderLargestModelsList();
        this.renderTagCloud();
        this.renderInsights();
    }

    renderMetricsCards() {
        const metricsGrid = document.getElementById('metricsGrid');
        if (!metricsGrid || !this.data.collection) return;

        const metrics = [
            {
                icon: 'fas fa-magic',
                value: this.data.collection.total_models,
                label: translate('statistics.metrics.totalModels'),
                format: 'number'
            },
            {
                icon: 'fas fa-database',
                value: this.data.collection.total_size,
                label: translate('statistics.metrics.totalStorage'),
                format: 'size'
            },
            {
                icon: 'fas fa-play-circle',
                value: this.data.collection.total_generations,
                label: translate('statistics.metrics.totalGenerations'),
                format: 'number'
            },
            {
                icon: 'fas fa-chart-line',
                value: this.calculateUsageRate(),
                label: translate('statistics.metrics.usageRate'),
                format: 'percentage'
            },
            {
                icon: 'fas fa-layer-group',
                value: this.data.collection.lora_count,
                label: translate('statistics.metrics.loras'),
                format: 'number'
            },
            {
                icon: 'fas fa-check-circle',
                value: this.data.collection.checkpoint_count,
                label: translate('statistics.metrics.checkpoints'),
                format: 'number'
            },
            {
                icon: 'fas fa-code',
                value: this.data.collection.embedding_count,
                label: translate('statistics.metrics.embeddings'),
                format: 'number'
            }
        ];

        metricsGrid.innerHTML = metrics.map(metric => this.createMetricCard(metric)).join('');
    }

    createMetricCard(metric) {
        const formattedValue = this.formatValue(metric.value, metric.format);
        
        return `
            <div class="metric-card">
                <div class="metric-icon">
                    <i class="${metric.icon}"></i>
                </div>
                <div class="metric-value">${formattedValue}</div>
                <div class="metric-label">${metric.label}</div>
            </div>
        `;
    }

    formatValue(value, format) {
        switch (format) {
            case 'number':
                return new Intl.NumberFormat().format(value);
            case 'size':
                return this.formatFileSize(value);
            case 'percentage':
                return new Intl.NumberFormat(i18n.getCurrentLocale(), { style: 'percent', maximumFractionDigits: 1 }).format(value / 100);
            default:
                return value;
        }
    }

    formatFileSize(bytes) {
        return i18n.formatFileSize(bytes);
    }

    calculateUsageRate() {
        if (!this.data.collection) return 0;
        
        const totalModels = this.data.collection.total_models;
        const unusedModels = this.data.collection.unused_loras + 
                           this.data.collection.unused_checkpoints + 
                           this.data.collection.unused_embeddings;
        const usedModels = totalModels - unusedModels;
        
        return totalModels > 0 ? (usedModels / totalModels) * 100 : 0;
    }

    initializeCharts() {
        // Check if Chart.js is available
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not available. Charts will not be rendered.');
            this.showChartPlaceholders();
            return;
        }

        // Collection pie chart
        this.createCollectionPieChart();
        
        // Base model distribution chart
        this.createBaseModelChart();
        
        // Usage timeline chart
        this.createUsageTimelineChart();
        
        // Usage distribution chart
        this.createUsageDistributionChart();
        
        // Storage chart
        this.createStorageChart();
        
        // Storage efficiency chart
        this.createStorageEfficiencyChart();
        
        // Model types chart (Collection tab)
        this.createModelTypesChart();
    }

    createCollectionPieChart() {
        const ctx = document.getElementById('collectionPieChart');
        if (!ctx || !this.data.collection) return;

        const data = {
            labels: [translate('statistics.metrics.loras'), translate('statistics.metrics.checkpoints'), translate('statistics.metrics.embeddings')],
            datasets: [{
                data: [
                    this.data.collection.lora_count, 
                    this.data.collection.checkpoint_count,
                    this.data.collection.embedding_count
                ],
                backgroundColor: [
                    'oklch(68% 0.28 256)',
                    'oklch(68% 0.28 200)',
                    'oklch(68% 0.28 120)'
                ],
                borderWidth: 2,
                borderColor: getComputedStyle(document.documentElement).getPropertyValue('--border-color')
            }]
        };

        this.charts.collection = new Chart(ctx, {
            type: 'doughnut',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    createBaseModelChart() {
        const ctx = document.getElementById('baseModelChart');
        if (!ctx || !this.data.baseModels) return;

        const loraData = this.data.baseModels.loras;
        const checkpointData = this.data.baseModels.checkpoints;
        const embeddingData = this.data.baseModels.embeddings;
        
        const allModels = Array.from(new Set([
            ...Object.keys(loraData), 
            ...Object.keys(checkpointData),
            ...Object.keys(embeddingData)
        ])).sort();
        
        const data = {
            labels: allModels,
            datasets: [
                {
                    label: translate('statistics.metrics.loras'),
                    data: allModels.map(model => loraData[model] || 0),
                    backgroundColor: 'oklch(68% 0.28 256 / 0.7)'
                },
                {
                    label: translate('statistics.metrics.checkpoints'),
                    data: allModels.map(model => checkpointData[model] || 0),
                    backgroundColor: 'oklch(68% 0.28 200 / 0.7)'
                },
                {
                    label: translate('statistics.metrics.embeddings'),
                    data: allModels.map(model => embeddingData[model] || 0),
                    backgroundColor: 'oklch(68% 0.28 120 / 0.7)'
                }
            ]
        };

        this.charts.baseModels = new Chart(ctx, {
            type: 'bar',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        stacked: true
                    },
                    y: {
                        stacked: true
                    }
                }
            }
        });
    }

    createUsageTimelineChart() {
        const ctx = document.getElementById('usageTimelineChart');
        if (!ctx || !this.data.usage) return;

        const timeline = this.data.usage.usage_timeline || [];
        
        const data = {
            labels: timeline.map(item => new Date(item.date).toLocaleDateString()),
            datasets: [
                {
                    label: translate('statistics.charts.loraUsage'),
                    data: timeline.map(item => item.lora_usage),
                    borderColor: 'oklch(68% 0.28 256)',
                    backgroundColor: 'oklch(68% 0.28 256 / 0.1)',
                    fill: true
                },
                {
                    label: translate('statistics.charts.checkpointUsage'),
                    data: timeline.map(item => item.checkpoint_usage),
                    borderColor: 'oklch(68% 0.28 200)',
                    backgroundColor: 'oklch(68% 0.28 200 / 0.1)',
                    fill: true
                },
                {
                    label: translate('statistics.charts.embeddingUsage'),
                    data: timeline.map(item => item.embedding_usage),
                    borderColor: 'oklch(68% 0.28 120)',
                    backgroundColor: 'oklch(68% 0.28 120 / 0.1)',
                    fill: true
                }
            ]
        };

        this.charts.timeline = new Chart(ctx, {
            type: 'line',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                scales: {
                    x: {
                        display: true,
                        title: {
                            display: true,
                            text: translate('statistics.charts.date')
                        }
                    },
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: translate('statistics.charts.usageCount')
                        }
                    }
                }
            }
        });
    }

    createUsageDistributionChart() {
        const ctx = document.getElementById('usageDistributionChart');
        if (!ctx || !this.data.usage) return;

        const topLoras = this.data.usage.top_loras || [];
        const topCheckpoints = this.data.usage.top_checkpoints || [];
        const topEmbeddings = this.data.usage.top_embeddings || [];
        
        // Combine and sort all models by usage
        const allModels = [
            ...topLoras.map(m => ({ ...m, type: 'LoRA' })),
            ...topCheckpoints.map(m => ({ ...m, type: 'Checkpoint' })),
            ...topEmbeddings.map(m => ({ ...m, type: 'Embedding' }))
        ].sort((a, b) => b.usage_count - a.usage_count).slice(0, 10);

        const data = {
            labels: allModels.map(model => model.name),
            datasets: [{
                label: translate('statistics.charts.usageCount'),
                data: allModels.map(model => model.usage_count),
                backgroundColor: allModels.map(model => {
                    switch(model.type) {
                        case 'LoRA': return 'oklch(68% 0.28 256)';
                        case 'Checkpoint': return 'oklch(68% 0.28 200)';
                        case 'Embedding': return 'oklch(68% 0.28 120)';
                        default: return 'oklch(68% 0.28 256)';
                    }
                })
            }]
        };

        this.charts.distribution = new Chart(ctx, {
            type: 'bar',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    createStorageChart() {
        const ctx = document.getElementById('storageChart');
        if (!ctx || !this.data.collection) return;

        const data = {
            labels: [translate('statistics.metrics.loras'), translate('statistics.metrics.checkpoints'), translate('statistics.metrics.embeddings')],
            datasets: [{
                data: [
                    this.data.collection.lora_size, 
                    this.data.collection.checkpoint_size,
                    this.data.collection.embedding_size
                ],
                backgroundColor: [
                    'oklch(68% 0.28 256)',
                    'oklch(68% 0.28 200)',
                    'oklch(68% 0.28 120)'
                ]
            }]
        };

        this.charts.storage = new Chart(ctx, {
            type: 'doughnut',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const value = this.formatFileSize(context.raw);
                                return `${context.label}: ${value}`;
                            }
                        }
                    }
                }
            }
        });
    }

    createStorageEfficiencyChart() {
        const ctx = document.getElementById('storageEfficiencyChart');
        if (!ctx || !this.data.storage) return;

        const loraData = this.data.storage.loras || [];
        const checkpointData = this.data.storage.checkpoints || [];
        const embeddingData = this.data.storage.embeddings || [];
        
        const allData = [
            ...loraData.map(item => ({ ...item, type: 'LoRA' })),
            ...checkpointData.map(item => ({ ...item, type: 'Checkpoint' })),
            ...embeddingData.map(item => ({ ...item, type: 'Embedding' }))
        ];

        const data = {
            datasets: [{
                label: translate('statistics.charts.models'),
                data: allData.map(item => ({
                    x: item.size,
                    y: item.usage_count,
                    name: item.name,
                    type: item.type
                })),
                backgroundColor: allData.map(item => {
                    switch(item.type) {
                        case 'LoRA': return 'oklch(68% 0.28 256 / 0.6)';
                        case 'Checkpoint': return 'oklch(68% 0.28 200 / 0.6)';
                        case 'Embedding': return 'oklch(68% 0.28 120 / 0.6)';
                        default: return 'oklch(68% 0.28 256 / 0.6)';
                    }
                })
            }]
        };

        this.charts.efficiency = new Chart(ctx, {
            type: 'scatter',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: translate('statistics.charts.fileSizeBytes')
                        },
                        type: 'logarithmic'
                    },
                    y: {
                        title: {
                            display: true,
                            text: translate('statistics.charts.usageCount')
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const point = context.raw;
                                return translate('statistics.tooltips.chartUsage', { name: point.name, size: this.formatFileSize(point.x), count: point.y });
                            }
                        }
                    }
                }
            }
        });
    }

    createModelTypesChart() {
        const ctx = document.getElementById('modelTypesChart');
        if (!ctx || !this.data.collection || !this.data.collection.model_types_distribution) return;

        const distribution = this.data.collection.model_types_distribution;
        const typeDisplayNames = {
            lora: translate('statistics.modelTypes.lora'),
            locon: translate('statistics.modelTypes.locon'),
            dora: translate('statistics.modelTypes.dora'),
            checkpoint: translate('statistics.modelTypes.checkpoint'),
            diffusion_model: translate('statistics.modelTypes.diffusion_model'),
            embedding: translate('statistics.modelTypes.embedding')
        };

        const colorPalette = {
            lora: 'oklch(68% 0.28 256)',
            locon: 'oklch(68% 0.25 190)',
            dora: 'oklch(68% 0.25 330)',
            checkpoint: 'oklch(68% 0.28 45)',
            diffusion_model: 'oklch(68% 0.25 280)',
            embedding: 'oklch(68% 0.25 120)'
        };

        const labels = Object.keys(distribution).map(k => typeDisplayNames[k] || k);
        const values = Object.values(distribution);
        const colors = Object.keys(distribution).map(k => colorPalette[k] || 'oklch(68% 0.15 0)');

        const data = {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderColor: getComputedStyle(document.documentElement).getPropertyValue('--border-color'),
                borderWidth: 2
            }]
        };

        this.charts.modelTypes = new Chart(ctx, {
            type: 'doughnut',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const value = context.parsed;
                                const pct = ((value / total) * 100).toFixed(1);
                                return translate('statistics.tooltips.chartPercentage', { label: context.label, value, pct });
                            }
                        }
                    }
                }
            }
        });
    }

    async initializeLists() {
        const listTypes = [
            { type: 'lora', containerId: 'topLorasList' },
            { type: 'checkpoint', containerId: 'topCheckpointsList' },
            { type: 'embedding', containerId: 'topEmbeddingsList' }
        ];

        const promises = listTypes.map(({ type, containerId }) => {
            const container = document.getElementById(containerId);
            
            if (container) {
                // Handle infinite scrolling
                container.addEventListener('scroll', () => {
                    if (container.scrollTop + container.clientHeight >= container.scrollHeight - 50) {
                        this.fetchAndRenderList(type, container);
                    }
                });

                // Initial fetch
                return this.fetchAndRenderList(type, container);
            }
            return Promise.resolve();
        });

        await Promise.all(promises);
    }

    async fetchAndRenderList(type, container) {
        const state = this.listStates[type];
        if (state.isLoading || !state.hasMore) return;

        state.isLoading = true;
        
        // Show loading indicator on initial load
        if (state.offset === 0) {
            container.innerHTML = '<div class="loading-placeholder"><i class="fas fa-spinner fa-spin"></i> ' + translate('statistics.placeholders.loading') + '</div>';
        }

        try {
            const url = `/api/lm/stats/model-usage-list?type=${type}&sort=${state.sort}&offset=${state.offset}&limit=${state.limit}`;
            const result = await this.fetchData(url);
            
            if (result.success) {
                const items = result.data.items;
                
                // Remove loading indicator if it's the first page
                if (state.offset === 0) {
                    container.innerHTML = '';
                }

                if (items.length === 0 && state.offset === 0) {
                    container.innerHTML = '<div class="loading-placeholder">' + translate('statistics.placeholders.noModels') + '</div>';
                    state.hasMore = false;
                } else if (items.length < state.limit) {
                    state.hasMore = false;
                }

                const html = items.map(model => `
                    <div class="model-item">
                        <img src="${model.preview_url || '/loras_static/images/no-preview.png'}" 
                             alt="${model.name}" class="model-preview" 
                             onerror="this.src='/loras_static/images/no-preview.png'">
                        <div class="model-info">
                            <div class="model-name" title="${model.name}">${model.name}</div>
                            <div class="model-meta">${model.base_model} • ${model.folder || translate('statistics.placeholders.rootFolder')}</div>
                        </div>
                        <div class="model-usage">${model.usage_count}</div>
                    </div>
                `).join('');

                container.insertAdjacentHTML('beforeend', html);
                state.offset += state.limit;
            }
        } catch (error) {
            console.error(`Error loading ${type} list:`, error);
            if (state.offset === 0) {
                container.innerHTML = '<div class="loading-placeholder">' + translate('statistics.placeholders.errorLoading') + '</div>';
            }
        } finally {
            state.isLoading = false;
        }
    }

    renderLargestModelsList() {
        const container = document.getElementById('largestModelsList');
        if (!container || !this.data.storage) return;

        const loraModels = this.data.storage.loras || [];
        const checkpointModels = this.data.storage.checkpoints || [];
        const embeddingModels = this.data.storage.embeddings || [];
        
        // Combine and sort by size
        const allModels = [
            ...loraModels.map(m => ({ ...m, type: 'LoRA' })),
            ...checkpointModels.map(m => ({ ...m, type: 'Checkpoint' })),
            ...embeddingModels.map(m => ({ ...m, type: 'Embedding' }))
        ].sort((a, b) => b.size - a.size).slice(0, 10);

        if (allModels.length === 0) {
            container.innerHTML = '<div class="loading-placeholder">' + translate('statistics.placeholders.noStorageData') + '</div>';
            return;
        }

        container.innerHTML = allModels.map(model => `
            <div class="model-item">
                <div class="model-info">
                    <div class="model-name" title="${model.name}">${model.name}</div>
                    <div class="model-meta">${translate('statistics.modelTypes.' + model.type.toLowerCase())} • ${model.base_model}</div>
                </div>
                <div class="model-usage">${this.formatFileSize(model.size)}</div>
            </div>
        `).join('');
    }

    renderTagCloud() {
        const container = document.getElementById('tagCloud');
        if (!container || !this.data.tags?.top_tags) return;

        const topTags = this.data.tags.top_tags.slice(0, 30); // Show top 30 tags
        const maxCount = Math.max(...topTags.map(tag => tag.count));
        
        container.innerHTML = topTags.map(tagData => {
            const size = Math.ceil((tagData.count / maxCount) * 5);
            return `
                <span class="tag-cloud-item size-${size}" 
                      title="${translate('statistics.tooltips.tagCount', { tag: tagData.tag, count: tagData.count })}">
                    ${tagData.tag}
                </span>
            `;
        }).join('');
    }

    renderInsights() {
        const container = document.getElementById('insightsList');
        if (!container || !this.data.insights?.insights) return;

        const insights = this.data.insights.insights;
        
        if (insights.length === 0) {
            container.innerHTML = '<div class="loading-placeholder">' + translate('statistics.insights.noInsights') + '</div>';
            return;
        }

        container.innerHTML = insights.map(insight => {
            const params = insight.params || {};
            let title, description, suggestion;
            if (insight.key) {
                title = translate('statistics.' + insight.key + '.title', params);
                description = translate('statistics.' + insight.key + '.description', params);
                suggestion = translate('statistics.' + insight.key + '.suggestion', params);
            } else {
                // Backward compatibility for insights without key/params
                title = insight.title || '';
                description = insight.description || '';
                suggestion = insight.suggestion || '';
            }
            return `
            <div class="insight-card type-${insight.type}">
                <div class="insight-title">${title}</div>
                <div class="insight-description">${description}</div>
                <div class="insight-suggestion">${suggestion}</div>
            </div>
        `}).join('');

        // Render collection analysis cards
        this.renderCollectionAnalysis();
    }

    renderCollectionAnalysis() {
        const container = document.getElementById('collectionAnalysis');
        if (!container || !this.data.collection) return;

        const analysis = [
            {
                icon: 'fas fa-percentage',
                value: this.calculateUsageRate(),
                label: translate('statistics.metrics.usageRate'),
                format: 'percentage'
            },
            {
                icon: 'fas fa-tags',
                value: this.data.tags?.total_unique_tags || 0,
                label: translate('statistics.metrics.uniqueTags'),
                format: 'number'
            },
            {
                icon: 'fas fa-clock',
                value: this.data.collection.unused_loras + this.data.collection.unused_checkpoints,
                label: translate('statistics.metrics.unusedModels'),
                format: 'number'
            },
            {
                icon: 'fas fa-chart-line',
                value: this.calculateAverageUsage(),
                label: translate('statistics.metrics.avgUsesPerModel'),
                format: 'decimal'
            }
        ];

        container.innerHTML = analysis.map(item => `
            <div class="analysis-card">
                <div class="card-icon">
                    <i class="${item.icon}"></i>
                </div>
                <div class="card-value">${this.formatValue(item.value, item.format)}</div>
                <div class="card-label">${item.label}</div>
            </div>
        `).join('');
    }

    calculateAverageUsage() {
        if (!this.data.usage || !this.data.collection) return 0;
        
        const totalGenerations = this.data.collection.total_generations;
        const totalModels = this.data.collection.total_models;
        
        return totalModels > 0 ? totalGenerations / totalModels : 0;
    }

    showChartPlaceholders() {
        const chartCanvases = document.querySelectorAll('canvas');
        chartCanvases.forEach(canvas => {
            const container = canvas.parentElement;
            container.innerHTML = '<div class="loading-placeholder"><i class="fas fa-chart-bar"></i> ' + translate('statistics.placeholders.chartLibraryMissing') + '</div>';
        });
    }

    refreshChartsInPanel(panelId) {
        // Refresh charts when panels become visible
        setTimeout(() => {
            Object.values(this.charts).forEach(chart => {
                if (chart && typeof chart.resize === 'function') {
                    chart.resize();
                }
            });
        }, 100);
    }

    destroy() {
        // Clean up charts
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
        this.charts = {};
        this.initialized = false;
    }
}

// Initialize statistics page when DOM is ready
document.addEventListener('DOMContentLoaded', async () => {
    // Wait for app core to initialize
    await appCore.initialize();
    
    // Initialize statistics functionality
    const statsManager = new StatisticsManager();
    await statsManager.initialize();
    
    // Make statsManager globally available for debugging
    window.statsManager = statsManager;
    
    console.log('Statistics page initialized successfully');
});

// Handle page unload
window.addEventListener('beforeunload', () => {
    if (window.statsManager) {
        window.statsManager.destroy();
    }
});