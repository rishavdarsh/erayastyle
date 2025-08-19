// Exact sidebar JavaScript from /hub
let sidebarCollapsed = false;

function toggleSidebar() {
    if (window.innerWidth >= 768) {
        // Desktop behavior
        sidebarCollapsed = !sidebarCollapsed;
        if (sidebarCollapsed) {
            sidebar.classList.add('collapsed');
            sidebarToggle.innerHTML = '<span class="text-lg">⟩</span>';
        } else {
            sidebar.classList.remove('collapsed');
            sidebarToggle.innerHTML = '<span class="text-lg">⟨</span>';
        }
        localStorage.setItem('sidebarCollapsed', sidebarCollapsed.toString());
        document.querySelector('.main-content').style.marginLeft = sidebarCollapsed ? '80px' : '280px';
    } else {
        // Mobile behavior
        sidebar.classList.toggle('mobile-open');
    }
}

// Initialize sidebar
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const mainContent = document.querySelector('.main-content');

    // Restore sidebar collapsed state
    const savedCollapsed = localStorage.getItem('sidebarCollapsed');
    if (savedCollapsed === 'true' && window.innerWidth >= 768) {
        sidebarCollapsed = true;
        sidebar.classList.add('collapsed');
        mainContent.style.marginLeft = '80px';
        sidebarToggle.innerHTML = '<span class="text-lg">⟩</span>';
    }

    // Wire up toggle button
    sidebarToggle.addEventListener('click', toggleSidebar);

    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 768) {
            sidebar.classList.remove('mobile-open');
            mainContent.style.marginLeft = sidebarCollapsed ? '80px' : '280px';
        } else {
            mainContent.style.marginLeft = '0';
        }
    });

    // Close mobile sidebar when clicking outside
    document.addEventListener('click', function(e) {
        if (window.innerWidth < 768 && !sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
            sidebar.classList.remove('mobile-open');
        }
    });
});