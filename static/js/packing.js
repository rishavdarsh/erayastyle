/**
 * Packing Management JavaScript
 * Handles CSV/XLSX file upload, parsing, table display, filtering, and export
 */

class PackingManager {
    constructor() {
        this.data = [];
        this.filteredData = [];
        this.columns = [];
        this.detectedColumns = {};
        this.imageLinkColumns = []; // New: track image link columns
        this.currentPage = 1;
        this.pageSize = 1000; // Default to 1000 rows per page
        this.sortColumn = null;
        this.sortDirection = 'asc'; // 'asc' or 'desc'
        this.filters = {
            order: '',
            product: '',
            variant: '',
            status: '',
            sku: '',
            variantType: '',
            packer: ''
        };
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.updateStatus('Ready to upload file');
    }

    bindEvents() {
        // File handling
        document.getElementById('chooseFileBtn').addEventListener('click', () => {
            document.getElementById('fileInput').click();
        });

        document.getElementById('fileInput').addEventListener('change', (e) => {
            this.handleFileSelect(e.target.files[0]);
        });

        document.getElementById('previewBtn').addEventListener('click', () => {
            this.previewData();
        });

        document.getElementById('exportBtn').addEventListener('click', () => {
            this.exportFilteredData();
        });

        document.getElementById('bulkActionBtn').addEventListener('click', () => {
            this.showBulkActions();
        });

        // Filters
        document.getElementById('searchOrder').addEventListener('input', (e) => {
            this.filters.order = e.target.value;
            this.applyFilters();
        });

        document.getElementById('searchProduct').addEventListener('input', (e) => {
            this.filters.product = e.target.value;
            this.applyFilters();
        });

        document.getElementById('searchVariant').addEventListener('input', (e) => {
            this.filters.variant = e.target.value;
            this.applyFilters();
        });

        document.getElementById('filterStatus').addEventListener('change', (e) => {
            this.filters.status = e.target.value;
            this.applyFilters();
        });

        document.getElementById('filterSku').addEventListener('change', (e) => {
            this.filters.sku = e.target.value;
            this.applyFilters();
        });

        document.getElementById('filterVariant').addEventListener('change', (e) => {
            this.filters.variantType = e.target.value;
            this.applyFilters();
        });

        document.getElementById('filterPacker').addEventListener('change', (e) => {
            this.filters.packer = e.target.value;
            this.applyFilters();
        });

        // Pagination
        document.getElementById('pageSize').addEventListener('change', (e) => {
            this.pageSize = parseInt(e.target.value);
            this.currentPage = 1;
            this.renderTable();
        });

        document.getElementById('prevPage').addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.renderTable();
            }
        });

        document.getElementById('nextPage').addEventListener('click', () => {
            const maxPage = Math.ceil(this.filteredData.length / this.pageSize);
            if (this.currentPage < maxPage) {
                this.currentPage++;
                this.renderTable();
            }
        });
    }

    async handleFileSelect(file) {
        if (!file) return;

        this.updateStatus('Processing file...');
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('previewBtn').disabled = false;

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/packing/preview', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            if (result.success) {
                this.data = result.data.rows || [];
                this.columns = result.data.columns || [];
                this.detectedColumns = result.data.detected_columns || {};
                this.imageLinkColumns = result.data.image_link_columns || []; // New: store image link columns
                
                // Debug logging
                console.log('🔍 Columns:', this.columns);
                console.log('🖼️ Image Link Columns:', this.imageLinkColumns);
                console.log('📊 Sample data:', this.data.slice(0, 2));
                
                // Add row index to each row for checkbox functionality
                this.data.forEach((row, index) => {
                    row._rowIndex = index;
                });
                
                this.updateStatus(`Loaded ${this.data.length} rows with ${this.columns.length} columns (${this.imageLinkColumns.length} image columns)`);
                this.populateFilterOptions();
                this.applyFilters();
                this.showWarningIfNeeded();
                
                // Enable buttons
                document.getElementById('exportBtn').disabled = false;
                document.getElementById('bulkActionBtn').disabled = false;
            } else {
                throw new Error(result.error || 'Failed to process file');
            }
        } catch (error) {
            console.error('Error processing file:', error);
            this.updateStatus(`Error: ${error.message}`);
            this.showError(`Failed to process file: ${error.message}`);
        }
    }

    populateFilterOptions() {
        // Auto-detect SKU column from any column that might contain SKUs
        const skuColumns = this.columns.filter(col => 
            col.toLowerCase().includes('sku') || 
            col.toLowerCase().includes('variant') ||
            col.toLowerCase().includes('product')
        );
        
        // Populate SKU filter from all detected SKU-like columns
        const skuFilter = document.getElementById('filterSku');
        const allSkus = new Set();
        
        skuColumns.forEach(col => {
            this.data.forEach(row => {
                const value = row[col];
                if (value && value.trim() && value.length < 50) { // Reasonable SKU length
                    allSkus.add(value.trim());
                }
            });
        });
        
        const skus = [...allSkus].sort();
        skuFilter.innerHTML = '<option value="">All SKUs</option>' + 
            skus.map(sku => `<option value="${sku}">${sku}</option>`).join('');

        // Auto-detect Variant columns
        const variantColumns = this.columns.filter(col => 
            col.toLowerCase().includes('variant') || 
            col.toLowerCase().includes('color') ||
            col.toLowerCase().includes('size') ||
            col.toLowerCase().includes('type')
        );
        
        // Populate variant filter from all detected variant-like columns
        const variantFilter = document.getElementById('filterVariant');
        const allVariants = new Set();
        
        variantColumns.forEach(col => {
            this.data.forEach(row => {
                const value = row[col];
                if (value && value.trim() && value.length < 100) { // Reasonable variant length
                    allVariants.add(value.trim());
                }
            });
        });
        
        const variants = [...allVariants].sort();
        variantFilter.innerHTML = '<option value="">All Variants</option>' + 
            variants.map(variant => `<option value="${variant}">${variant}</option>`).join('');

        // Populate packer filter (if packer column exists)
        const packerFilter = document.getElementById('filterPacker');
        const packerCol = this.columns.find(col => col.toLowerCase().includes('packer') || col.toLowerCase().includes('assigned'));
        if (packerCol) {
            const packers = [...new Set(this.data.map(row => row[packerCol] || '').filter(Boolean))];
            packerFilter.innerHTML = '<option value="">All Packers</option>' + 
                packers.map(packer => `<option value="${packer}">${packer}</option>`).join('');
        }
        
        console.log('🔧 Filter options populated:', {
            skus: skus.length,
            variants: variants.length,
            skuColumns,
            variantColumns
        });
    }

    applyFilters() {
        this.filteredData = this.data.filter(row => {
            // Order filter
            if (this.filters.order) {
                const orderColumns = this.columns.filter(col => 
                    col.toLowerCase().includes('order') || 
                    col.toLowerCase().includes('number') ||
                    col.toLowerCase().includes('id')
                );
                
                let found = false;
                for (const col of orderColumns) {
                    const orderValue = row[col] || '';
                    if (orderValue.toLowerCase().includes(this.filters.order.toLowerCase())) {
                        found = true;
                        break;
                    }
                }
                if (!found) return false;
            }

            // Product filter
            if (this.filters.product) {
                const productColumns = this.columns.filter(col => 
                    col.toLowerCase().includes('product') || 
                    col.toLowerCase().includes('name') ||
                    col.toLowerCase().includes('title')
                );
                
                let found = false;
                for (const col of productColumns) {
                    const productValue = row[col] || '';
                    if (productValue.toLowerCase().includes(this.filters.product.toLowerCase())) {
                        found = true;
                        break;
                    }
                }
                if (!found) return false;
            }

            // Variant filter
            if (this.filters.variant) {
                const variantColumns = this.columns.filter(col => 
                    col.toLowerCase().includes('variant') || 
                    col.toLowerCase().includes('color') ||
                    col.toLowerCase().includes('size') ||
                    col.toLowerCase().includes('type')
                );
                
                let found = false;
                for (const col of variantColumns) {
                    const variantValue = row[col] || '';
                    if (variantValue.toLowerCase().includes(this.filters.variant.toLowerCase())) {
                        found = true;
                        break;
                    }
                }
                if (!found) return false;
            }

            // Status filter
            if (this.filters.status) {
                const statusInfo = this.getStatusInfo(row);
                if (statusInfo.overall_status !== this.filters.status) {
                    return false;
                }
            }

            // SKU filter - exact match against any SKU-like column
            if (this.filters.sku) {
                const skuColumns = this.columns.filter(col => 
                    col.toLowerCase().includes('sku') || 
                    col.toLowerCase().includes('variant') ||
                    col.toLowerCase().includes('product')
                );
                
                let found = false;
                for (const col of skuColumns) {
                    if (row[col] === this.filters.sku) {
                        found = true;
                        break;
                    }
                }
                if (!found) return false;
            }

            // Variant type filter - exact match against any variant-like column
            if (this.filters.variantType) {
                const variantColumns = this.columns.filter(col => 
                    col.toLowerCase().includes('variant') || 
                    col.toLowerCase().includes('color') ||
                    col.toLowerCase().includes('size') ||
                    col.toLowerCase().includes('type')
                );
                
                let found = false;
                for (const col of variantColumns) {
                    if (row[col] === this.filters.variantType) {
                        found = true;
                        break;
                    }
                }
                if (!found) return false;
            }

            // Packer filter
            if (this.filters.packer) {
                const packerCol = this.columns.find(col => col.toLowerCase().includes('packer') || col.toLowerCase().includes('assigned'));
                if (packerCol && row[packerCol] !== this.filters.packer) {
                    return false;
                }
            }

            return true;
        });

        // Apply sorting
        this.applySorting();

        this.currentPage = 1;
        this.renderTable();
        this.updateRowCount();
    }

    applySorting() {
        if (!this.sortColumn) return;
        
        this.filteredData.sort((a, b) => {
            const aVal = (a[this.sortColumn] || '').toString().toLowerCase();
            const bVal = (b[this.sortColumn] || '').toString().toLowerCase();
            
            let comparison = 0;
            if (aVal < bVal) comparison = -1;
            else if (aVal > bVal) comparison = 1;
            
            return this.sortDirection === 'desc' ? -comparison : comparison;
        });
    }

    getStatusInfo(row) {
        const statusInfo = {
            main_photo_status: 'OK',
            polaroid_status: 'OK',
            overall_status: 'OK'
        };

        // Check main photo status
        if (this.detectedColumns.main_photo_col) {
            const photoValue = row[this.detectedColumns.main_photo_col] || '';
            if (!this.isValidUrl(photoValue)) {
                statusInfo.main_photo_status = 'Missing Photo';
                statusInfo.overall_status = 'Missing Photo';
            }
        }

        // Check polaroid status
        if (this.detectedColumns.polaroid_count_col) {
            const polaroidValue = row[this.detectedColumns.polaroid_count_col] || '';
            try {
                const count = parseInt(polaroidValue) || 0;
                if (count === 0) {
                    statusInfo.polaroid_status = 'Missing Polaroid';
                    if (statusInfo.overall_status === 'OK') {
                        statusInfo.overall_status = 'Missing Polaroid';
                    }
                }
            } catch {
                if (!polaroidValue || polaroidValue.toLowerCase().match(/^(na|n\/a|null|none|)$/)) {
                    statusInfo.polaroid_status = 'Missing Polaroid';
                    if (statusInfo.overall_status === 'OK') {
                        statusInfo.overall_status = 'Missing Polaroid';
                    }
                }
            }
        }

        return statusInfo;
    }

    isValidUrl(url) {
        if (!url || url.toLowerCase().match(/^(na|n\/a|null|none|)$/)) {
            return false;
        }
        return url.startsWith('http://') || url.startsWith('https://') || url.startsWith('//');
    }

    renderTable() {
        const tableHead = document.getElementById('tableHead');
        const tableBody = document.getElementById('tableBody');

        if (!this.columns || this.columns.length === 0) {
            tableHead.innerHTML = '<tr><th>No data</th></tr>';
            tableBody.innerHTML = '<tr><td>Please upload a file</td></tr>';
            return;
        }

        // Render headers - show all actual CSV columns plus checkbox with sorting
        const orderColumns = this.columns.filter(col => 
            col.toLowerCase().includes('order') || 
            col.toLowerCase().includes('number') ||
            col.toLowerCase().includes('id')
        );
        
        tableHead.innerHTML = `
            <tr>
                <th class="checkbox-cell">
                    <input type="checkbox" id="selectAll" onchange="toggleSelectAll(this)">
                </th>
                ${this.columns.map(col => {
                    const isSortable = orderColumns.includes(col);
                    const sortIcon = this.sortColumn === col ? 
                        (this.sortDirection === 'asc' ? ' ▲' : ' ▼') : 
                        (isSortable ? ' ↕' : '');
                    
                    return `<th ${isSortable ? `class="sortable-header" onclick="packingManager.toggleSort('${col}')" style="cursor: pointer;"` : ''}>${col}${sortIcon}</th>`;
                }).join('')}
                <th>Status</th>
            </tr>
        `;

        // Calculate pagination
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = startIndex + this.pageSize;
        const pageData = this.filteredData.slice(startIndex, endIndex);

        // Render rows
        tableBody.innerHTML = pageData.map((row, index) => {
            const rowIndex = startIndex + index;
            row._rowIndex = rowIndex;
            
            return `
                <tr data-row-index="${rowIndex}">
                    <td class="checkbox-cell">
                        <input type="checkbox" class="row-checkbox" data-row-index="${rowIndex}">
                    </td>
                    ${this.columns.map(col => this.renderColumnCell(row, col)).join('')}
                    <td>
                        <select class="status-dropdown">
                            <option value="">-</option>
                            <option value="packed">Packed</option>
                            <option value="pending">Pending</option>
                            <option value="shipped">Shipped</option>
                        </select>
                    </td>
                </tr>
            `;
        }).join('');

        // Add event listeners to status dropdowns and checkboxes
        this.addStatusDropdownListeners();
        this.addCheckboxListeners();

        // Update pagination
        this.updatePagination();
    }

    toggleSort(columnName) {
        if (this.sortColumn === columnName) {
            // Toggle direction if same column
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            // New column, start with ascending
            this.sortColumn = columnName;
            this.sortDirection = 'asc';
        }
        
        this.applyFilters(); // This will re-sort and re-render
    }

    renderColumnCell(row, columnName) {
        const value = row[columnName] || '';
        
        // Check if this column should render as images
        if (this.imageLinkColumns.includes(columnName)) {
            return `<td>${this.renderImageLinksCell(value)}</td>`;
        }
        
        // Determine if this is a column that should wrap text (Product Name, Engraving, etc.)
        const shouldWrapText = columnName.toLowerCase().includes('product') || 
                              columnName.toLowerCase().includes('name') ||
                              columnName.toLowerCase().includes('engraving') ||
                              columnName.toLowerCase().includes('message') ||
                              columnName.toLowerCase().includes('description');
        
        if (shouldWrapText) {
            // For text-wrapping columns, don't truncate but add title for full text
            return `<td title="${value}" class="text-wrapping-cell">${value}</td>`;
        }
        
        // For other columns, only truncate if extremely long
        if (value && value.length > 50) {
            return `<td title="${value}">${value.substring(0, 47)}...</td>`;
        }
        return `<td>${value}</td>`;
    }

    renderCell(row, col, statusInfo) {
        // Check if this column should render as image links
        if (this.shouldRenderAsImageLinks(col)) {
            const rawValue = this.getColumnValue(row, col.key);
            return `<td>${this.renderImageLinksCell(rawValue)}</td>`;
        }

        switch (col.type) {
            case 'status':
                if (col.key === 'main_photo_status') {
                    return `<td><span class="status-badge ${this.getStatusClass(statusInfo.main_photo_status)}">${statusInfo.main_photo_status}</span></td>`;
                } else if (col.key === 'polaroid_count') {
                    return `<td><span class="status-badge ${this.getStatusClass(statusInfo.polaroid_status)}">${statusInfo.polaroid_status}</span></td>`;
                }
                return `<td><span class="status-badge status-ok">OK</span></td>`;
            
            case 'dropdown':
                return `<td>
                    <select class="status-dropdown">
                        <option value="">-</option>
                        <option value="packed">Packed</option>
                        <option value="pending">Pending</option>
                        <option value="shipped">Shipped</option>
                    </select>
                </td>`;
            
            default: // text
                const value = this.getColumnValue(row, col.key);
                if (value && value.length > 30) {
                    return `<td title="${value}">${value.substring(0, 30)}...</td>`;
                }
                return `<td>${value || ''}</td>`;
        }
    }

    shouldRenderAsImageLinks(col) {
        // Check if this column is in the image link columns list
        const columnKey = col.key;
        
        // Map column keys to actual column names
        const columnMapping = {
            'main_photo_col': this.detectedColumns.main_photo_col,
            'polaroid_count_col': this.detectedColumns.polaroid_count_col
        };
        
        const actualColumnName = columnMapping[columnKey];
        if (actualColumnName && this.imageLinkColumns.includes(actualColumnName)) {
            return true;
        }
        
        // Also check if any other column in imageLinkColumns should be rendered
        return this.imageLinkColumns.some(imgCol => {
            // Check if this column name contains the image column name
            return col.label.toLowerCase().includes(imgCol.toLowerCase()) || 
                   imgCol.toLowerCase().includes(col.label.toLowerCase());
        });
    }

    renderImageLinksCell(rawValue) {
        if (!rawValue || rawValue.toLowerCase().match(/^(na|n\/a|null|none|)$/)) {
            return '<span class="status-badge status-missing">Missing photo</span>';
        }

        // Extract URLs from the raw value
        const urls = this.extractUrlsFromText(rawValue);
        
        if (urls.length === 0) {
            return '<span class="status-badge status-missing">Missing photo</span>';
        }

        // Limit to first 6 images for performance
        const displayUrls = urls.slice(0, 6);
        const remainingCount = urls.length - 6;

        let html = '<div class="image-grid">';
        
        displayUrls.forEach((url, index) => {
            // Store URLs in a data attribute to avoid JSON stringification issues
            const urlsData = urls.join('|||'); // Use a unique separator
            html += `
                <img src="${url}" 
                     alt="Photo" 
                     loading="lazy" 
                     referrerpolicy="no-referrer"
                     style="max-width:64px; max-height:64px; object-fit:cover; border-radius:4px; margin-right:4px; margin-bottom:4px; cursor:pointer; border: 1px solid rgba(255,255,255,0.2);"
                     data-image-url="${url}"
                     data-all-urls="${urlsData}"
                     data-image-index="${index}"
                     onclick="packingManager.handleImageClick(this)"
                     onerror="this.style.display='none'; this.nextElementSibling && this.nextElementSibling.style.display='inline';"
                     class="photo-thumbnail">
                <span class="status-badge status-missing" style="display:none;">Missing photo</span>
            `;
        });

        // Show remaining count if there are more than 6 images
        if (remainingCount > 0) {
            html += `<span class="text-xs text-white/60 ml-2">+${remainingCount}</span>`;
        }

        html += '</div>';
        return html;
    }

    extractUrlsFromText(text) {
        if (!text) return [];
        
        // Split on common delimiters: comma, semicolon, newline, space
        const parts = text.split(/[,;\n\r\s]+/);
        
        const urls = [];
        for (const part of parts) {
            const trimmed = part.trim();
            if (trimmed && this.isValidUrl(trimmed)) {
                urls.push(trimmed);
            }
        }
        
        // Remove duplicates while preserving order
        return [...new Set(urls)];
    }

    handleImageClick(imageElement) {
        console.log('handleImageClick called'); // Debug log
        
        const imageUrl = imageElement.dataset.imageUrl;
        const allUrlsData = imageElement.dataset.allUrls;
        const currentIndex = parseInt(imageElement.dataset.imageIndex);
        
        if (!imageUrl) {
            console.error('No image URL found');
            return;
        }
        
        const allUrls = allUrlsData ? allUrlsData.split('|||') : [imageUrl];
        
        console.log('Image clicked:', imageUrl, allUrls, currentIndex); // Debug log
        
        try {
            this.openEnhancedImageModal(imageUrl, allUrls, currentIndex, imageElement);
        } catch (error) {
            console.error('Error opening modal:', error);
            // Fallback to simple alert for testing
            alert(`Image clicked: ${imageUrl}`);
        }
    }

    openEnhancedImageModal(imageUrl, allUrls = [imageUrl], currentIndex = 0, clickedElement = null) {
        // Find the row data to get the back engraving message
        let backMessage = '';
        
        if (clickedElement) {
            // Find the table row containing this image
            const row = clickedElement.closest('tr');
            if (row) {
                const rowIndex = parseInt(row.dataset.rowIndex);
                if (rowIndex !== undefined && this.filteredData[rowIndex]) {
                    // Look for back engraving value in the row data
                    const rowData = this.filteredData[rowIndex];
                    
                    // Search for back engraving VALUE columns (the actual engraving text for this order)
                    const engravingColumns = this.columns.filter(col => {
                        const colLower = col.toLowerCase();
                        return (colLower.includes('back') && colLower.includes('engraving') && colLower.includes('value')) ||
                               (colLower.includes('engraving') && colLower.includes('value')) ||
                               (colLower.includes('back') && colLower.includes('engraving')) ||
                               colLower === 'back engraving value' ||
                               colLower === 'engraving value' ||
                               colLower === 'back engraving';
                    });
                    
                    console.log('Found engraving value columns:', engravingColumns); // Debug log
                    console.log('Row data for order:', rowData); // Debug log
                    
                    if (engravingColumns.length > 0) {
                        backMessage = rowData[engravingColumns[0]] || '';
                        console.log(`Back engraving value from column "${engravingColumns[0]}":`, backMessage);
                    } else {
                        console.log('No back engraving value column found in:', this.columns);
                    }
                }
            }
        }
        
        console.log('Opening enhanced modal with:', {
            imageUrl,
            allUrls,
            currentIndex,
            backMessage,
            hasBackMessage: backMessage && backMessage.trim() && !backMessage.toLowerCase().match(/^(na|n\/a|null|none|-)$/)
        });
        
        this.currentModalImages = allUrls;
        this.currentModalIndex = currentIndex;
        this.currentBackMessage = backMessage;
        
        const modal = document.createElement('div');
        modal.id = 'enhancedImageModal';
        modal.className = 'fixed inset-0 bg-black/80 flex items-center justify-center z-50 image-modal';
        
        const hasNavigation = allUrls.length > 1;
        const hasBackMessage = backMessage && backMessage.trim() && 
                              !backMessage.toLowerCase().match(/^(na|n\/a|null|none|-)$/);
        
        modal.innerHTML = `
            <div class="relative bg-slate-800 rounded-xl p-6 image-modal-content">
                <button onclick="packingManager.closeEnhancedImageModal()" 
                        class="absolute top-3 right-3 text-white/70 hover:text-white text-2xl font-bold w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/10 transition-all">
                    ×
                </button>
                
                <div class="text-center">
                    <img id="enhancedModalImage" 
                         src="${imageUrl}" 
                         alt="Photo" 
                         class="max-w-full max-h-[60vh] object-contain rounded-lg shadow-lg"
                         style="max-width: 100%; height: auto;">
                    
                    ${hasNavigation ? `
                        <div class="mt-4 flex items-center justify-between">
                            <button onclick="packingManager.prevEnhancedModalImage()" 
                                    class="btn btn-secondary">← Prev</button>
                            <span class="text-white/70 text-sm" id="enhancedImageCounter">${currentIndex + 1} of ${allUrls.length}</span>
                            <button onclick="packingManager.nextEnhancedModalImage()" 
                                    class="btn btn-secondary">Next →</button>
                        </div>
                    ` : ''}
                    
                    ${hasBackMessage ? `
                        <div class="mt-6 text-left">
                            <div class="flex items-center justify-between mb-3">
                                <h4 class="text-white font-medium">Back Engraving Value:</h4>
                                <button onclick="packingManager.copyToClipboard(\`${backMessage.replace(/`/g, '\\`')}\`, this)" 
                                        class="copy-button flex items-center gap-2">
                                    📋 Copy Value
                                </button>
                            </div>
                            <div class="back-message-text" id="backMessageText">
                                "${backMessage}"
                            </div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close modal when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeEnhancedImageModal();
            }
        });
        
        // Close modal with Escape key
        document.addEventListener('keydown', this.handleEnhancedModalKeydown.bind(this));
        
        console.log('Modal created and added to DOM');
    }

    // Test function to verify modal works
    testModal() {
        // Create a fake element to simulate clicking from a row with back engraving
        const fakeElement = document.createElement('div');
        const fakeRow = document.createElement('tr');
        fakeRow.dataset.rowIndex = '0';
        fakeElement.appendChild(fakeRow);
        
        // Add fake data to test back engraving display
        this.filteredData = [{
            'Order Number': 'TEST123',
            'Back Engraving Value': 'Love you always ❤️',
            'Product Name': 'Test Product'
        }];
        this.columns = ['Order Number', 'Product Name', 'Back Engraving Value'];
        
        this.openEnhancedImageModal(
            'https://via.placeholder.com/400x300.jpg?text=Test+Image',
            ['https://via.placeholder.com/400x300.jpg?text=Test+Image'],
            0,
            fakeElement.firstChild
        );
    }

    openImageModal(urls, startIndex = 0) {
        this.currentModalImages = urls;
        this.currentModalIndex = startIndex;
        
        const modal = document.createElement('div');
        modal.id = 'imageModal';
        modal.className = 'fixed inset-0 bg-black/80 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="relative bg-slate-800 rounded-xl p-4 max-w-md mx-4">
                <button onclick="packingManager.closeImageModal()" class="absolute top-2 right-2 text-white/70 hover:text-white text-xl font-bold w-8 h-8 flex items-center justify-center">×</button>
                <div class="text-center">
                    <img id="modalImage" src="${urls[startIndex]}" alt="Photo" class="max-w-full max-h-80 object-contain rounded-lg">
                    <div class="mt-3 flex items-center justify-between">
                        ${urls.length > 1 ? `
                            <button onclick="packingManager.prevModalImage()" class="btn btn-secondary">← Prev</button>
                            <span class="text-white/70 text-sm">${startIndex + 1} of ${urls.length}</span>
                            <button onclick="packingManager.nextModalImage()" class="btn btn-secondary">Next →</button>
                        ` : '<div></div><div></div><div></div>'}
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close modal when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeImageModal();
            }
        });
        
        // Close modal with Escape key
        document.addEventListener('keydown', this.handleModalKeydown.bind(this));
    }

    closeImageModal() {
        const modal = document.getElementById('imageModal');
        if (modal) {
            modal.remove();
        }
        document.removeEventListener('keydown', this.handleModalKeydown.bind(this));
    }

    nextModalImage() {
        if (this.currentModalIndex < this.currentModalImages.length - 1) {
            this.currentModalIndex++;
            this.updateModalImage();
        }
    }

    prevModalImage() {
        if (this.currentModalIndex > 0) {
            this.currentModalIndex--;
            this.updateModalImage();
        }
    }

    updateModalImage() {
        const modalImage = document.getElementById('modalImage');
        const counter = document.querySelector('#imageModal .text-white\\/70');
        
        if (modalImage) {
            modalImage.src = this.currentModalImages[this.currentModalIndex];
        }
        if (counter) {
            counter.textContent = `${this.currentModalIndex + 1} of ${this.currentModalImages.length}`;
        }
    }

    handleModalKeydown(e) {
        if (e.key === 'Escape') {
            this.closeImageModal();
        } else if (e.key === 'ArrowLeft') {
            this.prevModalImage();
        } else if (e.key === 'ArrowRight') {
            this.nextModalImage();
        }
    }

    // Enhanced modal functions
    closeEnhancedImageModal() {
        const modal = document.getElementById('enhancedImageModal');
        if (modal) {
            modal.remove();
        }
        document.removeEventListener('keydown', this.handleEnhancedModalKeydown.bind(this));
    }

    nextEnhancedModalImage() {
        if (this.currentModalIndex < this.currentModalImages.length - 1) {
            this.currentModalIndex++;
            this.updateEnhancedModalImage();
        }
    }

    prevEnhancedModalImage() {
        if (this.currentModalIndex > 0) {
            this.currentModalIndex--;
            this.updateEnhancedModalImage();
        }
    }

    updateEnhancedModalImage() {
        const modalImage = document.getElementById('enhancedModalImage');
        const counter = document.getElementById('enhancedImageCounter');
        
        if (modalImage) {
            modalImage.src = this.currentModalImages[this.currentModalIndex];
        }
        if (counter) {
            counter.textContent = `${this.currentModalIndex + 1} of ${this.currentModalImages.length}`;
        }
    }

    handleEnhancedModalKeydown(e) {
        if (e.key === 'Escape') {
            this.closeEnhancedImageModal();
        } else if (e.key === 'ArrowLeft') {
            this.prevEnhancedModalImage();
        } else if (e.key === 'ArrowRight') {
            this.nextEnhancedModalImage();
        }
    }

    async copyToClipboard(text, buttonElement) {
        // Clean the text - remove any surrounding quotes or extra whitespace
        const cleanText = text.replace(/^["']|["']$/g, '').trim();
        
        try {
            await navigator.clipboard.writeText(cleanText);
            this.showToast(`Copied: "${cleanText}"`);
            
            // Briefly change button text to show success
            const originalText = buttonElement.innerHTML;
            buttonElement.innerHTML = '✅ Copied!';
            buttonElement.style.backgroundColor = '#10b981';
            
            setTimeout(() => {
                buttonElement.innerHTML = originalText;
                buttonElement.style.backgroundColor = '#2563eb';
            }, 1500);
        } catch (err) {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = cleanText;
            document.body.appendChild(textArea);
            textArea.select();
            
            try {
                document.execCommand('copy');
                this.showToast(`Copied: "${cleanText}"`);
                
                const originalText = buttonElement.innerHTML;
                buttonElement.innerHTML = '✅ Copied!';
                buttonElement.style.backgroundColor = '#10b981';
                
                setTimeout(() => {
                    buttonElement.innerHTML = originalText;
                    buttonElement.style.backgroundColor = '#2563eb';
                }, 1500);
            } catch (copyErr) {
                this.showToast('Failed to copy to clipboard', 'error');
            }
            
            document.body.removeChild(textArea);
        }
    }

    showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = 'toast-notification';
        if (type === 'error') {
            toast.style.backgroundColor = '#ef4444';
        }
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'toastSlideOut 0.3s ease-in';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        }, 3000);
    }

    getColumnValue(row, columnKey) {
        // Map column keys to actual CSV column names
        const columnMapping = {
            'packed': 'packed',
            'order_col': this.detectedColumns.order_col,
            'product_col': this.detectedColumns.product_col,
            'variant_col': this.detectedColumns.variant_col,
            'color_col': this.detectedColumns.color_col,
            'main_photo_col': this.detectedColumns.main_photo_col,
            'polaroid_count_col': this.detectedColumns.polaroid_count_col,
            'engrave_type_col': this.detectedColumns.engrave_type_col,
            'engrave_msg_col': this.detectedColumns.engrave_msg_col,
            'main_photo_status': 'main_photo_status',
            'polaroid_count': 'polaroid_count',
            'status': 'status'
        };
        
        const actualColumn = columnMapping[columnKey];
        if (!actualColumn) return '';
        
        return row[actualColumn] || '';
    }

    addStatusDropdownListeners() {
        const statusDropdowns = document.querySelectorAll('.status-dropdown');
        statusDropdowns.forEach((dropdown, index) => {
            dropdown.addEventListener('change', (e) => {
                const newStatus = e.target.value;
                const rowIndex = this.currentPage * this.pageSize - this.pageSize + index;
                if (this.filteredData[rowIndex]) {
                    this.filteredData[rowIndex].status = newStatus;
                    this.updateStatus(`Status updated for row ${rowIndex + 1}`);
                }
            });
        });
    }

    addCheckboxListeners() {
        const rowCheckboxes = document.querySelectorAll('.row-checkbox');
        const selectAllCheckbox = document.getElementById('selectAll');
        
        rowCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.updateBulkActionButton();
                this.updateSelectAllCheckbox();
            });
        });
    }

    updateBulkActionButton() {
        const selectedCount = document.querySelectorAll('.row-checkbox:checked').length;
        const bulkActionBtn = document.getElementById('bulkActionBtn');
        if (bulkActionBtn) {
            bulkActionBtn.disabled = selectedCount === 0;
        }
    }

    updateSelectAllCheckbox() {
        const totalCheckboxes = document.querySelectorAll('.row-checkbox').length;
        const checkedCheckboxes = document.querySelectorAll('.row-checkbox:checked').length;
        const selectAllCheckbox = document.getElementById('selectAll');
        
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = checkedCheckboxes === totalCheckboxes;
            selectAllCheckbox.indeterminate = checkedCheckboxes > 0 && checkedCheckboxes < totalCheckboxes;
        }
    }

    getStatusClass(status) {
        if (status.includes('Missing')) {
            return 'status-missing';
        } else if (status === 'OK') {
            return 'status-ok';
        } else {
            return 'status-warning';
        }
    }

    updatePagination() {
        const totalPages = Math.ceil(this.filteredData.length / this.pageSize);
        const pageInfo = document.getElementById('pageInfo');
        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        const paginationInfo = document.getElementById('paginationInfo');

        pageInfo.textContent = `Page ${this.currentPage} of ${totalPages}`;
        prevBtn.disabled = this.currentPage <= 1;
        nextBtn.disabled = this.currentPage >= totalPages;

        paginationInfo.textContent = `Showing ${(this.currentPage - 1) * this.pageSize + 1} to ${Math.min(this.currentPage * this.pageSize, this.filteredData.length)} of ${this.filteredData.length} rows`;
    }

    updateRowCount() {
        const rowCount = document.getElementById('rowCount');
        rowCount.textContent = `${this.filteredData.length} rows`;
    }

    updateStatus(message) {
        const status = document.getElementById('status');
        status.textContent = message;
    }

    showWarningIfNeeded() {
        // Always hide the warning banner since the table now dynamically displays all columns
        const warningBanner = document.getElementById('warningBanner');
        warningBanner.classList.add('hidden');
    }

    showBulkActions() {
        const selectedRows = this.getSelectedRows();
        if (selectedRows.length === 0) {
            this.showError('Please select rows first');
            return;
        }

        // Create bulk action modal
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-slate-800 p-6 rounded-xl max-w-md w-full mx-4">
                <h3 class="text-xl font-bold text-white mb-4">Bulk Actions (${selectedRows.length} rows)</h3>
                <div class="space-y-3">
                    <button class="w-full btn btn-primary" onclick="packingManager.bulkUpdateStatus('packed')">
                        Mark as Packed
                    </button>
                    <button class="w-full btn btn-secondary" onclick="packingManager.bulkUpdateStatus('pending')">
                        Mark as Pending
                    </button>
                    <button class="w-full btn btn-secondary" onclick="packingManager.bulkUpdateStatus('shipped')">
                        Mark as Shipped
                    </button>
                </div>
                <button class="w-full btn btn-secondary mt-4" onclick="this.closest('.fixed').remove()">
                    Cancel
                </button>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close modal when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
    }

    bulkUpdateStatus(status) {
        const selectedRows = this.getSelectedRows();
        selectedRows.forEach(row => {
            row.status = status;
        });
        
        this.renderTable();
        this.updateStatus(`Updated status to "${status}" for ${selectedRows.length} rows`);
        
        // Close modal
        const modal = document.querySelector('.fixed');
        if (modal) modal.remove();
    }

    showError(message) {
        // Create a simple error notification
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-red-600 text-white px-3 py-2 rounded-lg shadow-lg z-50';
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }

    toggleSelectAll(checkbox) {
        const rowCheckboxes = document.querySelectorAll('.row-checkbox');
        rowCheckboxes.forEach(cb => {
            cb.checked = checkbox.checked;
        });
        
        // Update bulk action button state
        const bulkActionBtn = document.getElementById('bulkActionBtn');
        if (bulkActionBtn) {
            bulkActionBtn.disabled = !checkbox.checked;
        }
    }

    getSelectedRows() {
        const selectedCheckboxes = document.querySelectorAll('.row-checkbox:checked');
        return Array.from(selectedCheckboxes).map(cb => {
            const rowIndex = parseInt(cb.dataset.rowIndex);
            return this.filteredData[rowIndex];
        });
    }

    async exportFilteredData() {
        if (this.filteredData.length === 0) {
            this.showError('No data to export');
            return;
        }

        try {
            // Use filtered and sorted data for export
            const dataToExport = [...this.filteredData]; // Make a copy to preserve current state
            
            // Convert data to CSV format with all original columns
            const csvContent = this.convertToCSV(dataToExport);
            
            // Create and download file
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            
            const timestamp = new Date().toISOString().split('T')[0];
            const filename = `packing_filtered_${timestamp}.csv`;
            
            link.setAttribute('href', url);
            link.setAttribute('download', filename);
            link.style.visibility = 'hidden';
            
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            this.updateStatus(`Exported ${this.filteredData.length} rows to ${filename}`);
        } catch (error) {
            console.error('Export error:', error);
            this.showError('Failed to export data');
        }
    }

    convertToCSV(data) {
        // Add BOM for Excel compatibility
        const BOM = '\uFEFF';
        
        if (data.length === 0) return BOM;
        
        // Use all original CSV columns to preserve complete data
        const headers = this.columns;
        
        // Create header row
        const headerRow = headers.map(header => {
            // Escape header if it contains special characters
            if (header.includes(',') || header.includes('"') || header.includes('\n')) {
                return `"${header.replace(/"/g, '""')}"`;
            }
            return header;
        }).join(',');
        
        // Create data rows
        const rows = data.map(row => {
            return headers.map(header => {
                const value = (row[header] || '').toString();
                // Escape commas, quotes, and newlines in CSV
                if (value.includes(',') || value.includes('"') || value.includes('\n')) {
                    return `"${value.replace(/"/g, '""')}"`;
                }
                return value;
            }).join(',');
        });
        
        return BOM + headerRow + '\n' + rows.join('\n');
    }

    previewData() {
        if (this.data.length === 0) {
            this.showError('No data to preview');
            return;
        }
        
        this.updateStatus(`Previewing ${this.data.length} rows`);
        this.renderTable();
    }
}

// Initialize the packing manager when the page loads
let packingManager;
document.addEventListener('DOMContentLoaded', () => {
    packingManager = new PackingManager();
});

// Global functions for HTML event handlers
function toggleSelectAll(checkbox) {
    if (packingManager) {
        packingManager.toggleSelectAll(checkbox);
    }
}
