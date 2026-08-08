export class ImportStepManager {
    constructor() {
        this.injectedStyles = null;
    }

    removeInjectedStyles() {
        if (this.injectedStyles && this.injectedStyles.parentNode) {
            this.injectedStyles.parentNode.removeChild(this.injectedStyles);
            this.injectedStyles = null;
        }
        
        // Reset inline styles
        document.querySelectorAll('.import-step').forEach(step => {
            step.style.cssText = '';
        });
    }

    showStep(stepId) {
        // Remove any injected styles to prevent conflicts
        this.removeInjectedStyles();
        
        // Hide all steps first
        document.querySelectorAll('.import-step').forEach(step => {
            step.style.display = 'none';
        });
        
        // Show target step with a monitoring mechanism
        const targetStep = document.getElementById(stepId);
        if (targetStep) {
            // Use direct style setting
            targetStep.style.display = 'block';
            
            // For the locationStep specifically, we need additional measures
            if (stepId === 'locationStep') {
                // Create a more persistent style to override any potential conflicts
                this.injectedStyles = document.createElement('style');
                this.injectedStyles.innerHTML = `
                    #locationStep {
                        display: block !important;
                        opacity: 1 !important;
                        visibility: visible !important;
                    }
                `;
                document.head.appendChild(this.injectedStyles);
                
                // Force layout recalculation
                targetStep.offsetHeight;
            }
            
            // Reset scroll via class: 'locationStep' has a duplicate ID in downloadModal's
            // template, so getElementById may not return the import modal's step.
            document.querySelectorAll('.import-step').forEach(step => {
                step.scrollTop = 0;
            });
        }
    }
}
