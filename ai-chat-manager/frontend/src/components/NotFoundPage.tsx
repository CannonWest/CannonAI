import { Link } from 'react-router-dom';
import { FiAlertCircle, FiHome } from 'react-icons/fi';

const NotFoundPage = () => {
  return (
    <div className="flex flex-col items-center justify-center h-full">
      <div className="text-center p-8">
        <div className="mb-6 text-red-500 dark:text-red-400">
          <FiAlertCircle className="h-16 w-16 mx-auto" />
        </div>
        <h1 className="text-4xl font-bold text-gray-800 dark:text-white mb-4">
          404 - Page Not Found
        </h1>
        <p className="text-gray-600 dark:text-gray-300 mb-8 max-w-md mx-auto">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <Link
          to="/"
          className="inline-flex items-center px-4 py-2 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          <FiHome className="mr-2" />
          Return Home
        </Link>
      </div>
    </div>
  );
};

export default NotFoundPage;
