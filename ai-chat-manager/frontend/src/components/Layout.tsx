import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import { useState } from 'react';
import { FiMenu, FiMoon, FiSun } from 'react-icons/fi';

interface LayoutProps {
  isDarkMode: boolean;
  toggleTheme: () => void;
}

const Layout = ({ isDarkMode, toggleTheme }: LayoutProps) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="flex h-screen bg-gray-100 dark:bg-gray-900">
      {/* Mobile sidebar toggle */}
      <div className="md:hidden fixed top-4 left-4 z-20">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-2 bg-white dark:bg-gray-800 rounded-md shadow-md"
        >
          <FiMenu className="h-5 w-5 text-gray-700 dark:text-gray-300" />
        </button>
      </div>

      {/* Theme toggle */}
      <div className="fixed top-4 right-4 z-20">
        <button
          onClick={toggleTheme}
          className="p-2 bg-white dark:bg-gray-800 rounded-md shadow-md"
        >
          {isDarkMode ? (
            <FiSun className="h-5 w-5 text-yellow-500" />
          ) : (
            <FiMoon className="h-5 w-5 text-gray-700" />
          )}
        </button>
      </div>

      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 transform ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        } md:translate-x-0 transition duration-200 ease-in-out z-10 w-64 bg-white dark:bg-gray-800 shadow-lg`}
      >
        <Sidebar closeSidebar={() => setSidebarOpen(false)} />
      </div>

      {/* Main content */}
      <div className="flex-1 md:ml-64 p-4 relative">
        <main className="h-full overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black bg-opacity-50 z-0"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
};

export default Layout;
