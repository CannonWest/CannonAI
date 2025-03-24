"""
Utility for properly cleaning up async resources 
when shutting down the application.
"""

import asyncio
import inspect
from typing import List, Any, Callable, Coroutine, Dict, Optional, Union
from src.utils.logging_utils import get_logger

# Get logger for this module
logger = get_logger(__name__)

async def cleanup_resources(resources: List[Any], timeout: float = 5.0):
    """
    Clean up multiple async resources, handling exceptions safely
    
    Args:
        resources: List of resources with cleanup/close methods
        timeout: Maximum time in seconds to wait for each resource cleanup
    """
    for resource in resources:
        try:
            await cleanup_resource(resource, timeout)
        except Exception as e:
            logger.error(f"Error cleaning up resource {resource}: {e}")

async def cleanup_resource(resource: Any, timeout: float = 5.0):
    """
    Properly clean up a single resource with timeout
    
    Args:
        resource: Resource to clean up
        timeout: Maximum time in seconds to wait for resource cleanup
    """
    resource_name = resource.__class__.__name__
    logger.debug(f"Cleaning up resource: {resource_name}")
    
    # First check for async cleanup/close methods
    if hasattr(resource, 'cleanup') and asyncio.iscoroutinefunction(resource.cleanup):
        try:
            await asyncio.wait_for(resource.cleanup(), timeout)
            logger.debug(f"Async cleanup completed for {resource_name}")
            return
        except asyncio.TimeoutError:
            logger.warning(f"Async cleanup timed out after {timeout}s for {resource_name}")
        except Exception as e:
            logger.error(f"Error in async cleanup for {resource_name}: {e}")
    
    # Next check for async close method
    elif hasattr(resource, 'close') and asyncio.iscoroutinefunction(resource.close):
        try:
            await asyncio.wait_for(resource.close(), timeout)
            logger.debug(f"Async close completed for {resource_name}")
            return
        except asyncio.TimeoutError:
            logger.warning(f"Async close timed out after {timeout}s for {resource_name}")
        except Exception as e:
            logger.error(f"Error in async close for {resource_name}: {e}")
    
    # Next check for regular (non-async) cleanup/close methods
    elif hasattr(resource, 'cleanup'):
        try:
            resource.cleanup()
            logger.debug(f"Sync cleanup completed for {resource_name}")
            return
        except Exception as e:
            logger.error(f"Error in sync cleanup for {resource_name}: {e}")
    
    elif hasattr(resource, 'close'):
        try:
            resource.close()
            logger.debug(f"Sync close completed for {resource_name}")
            return
        except Exception as e:
            logger.error(f"Error in sync close for {resource_name}: {e}")
    
    # Check for other possible cleanup methods
    elif hasattr(resource, 'disconnect'):
        try:
            # Could be async or sync
            if asyncio.iscoroutinefunction(resource.disconnect):
                await asyncio.wait_for(resource.disconnect(), timeout)
            else:
                resource.disconnect()
            logger.debug(f"Disconnect completed for {resource_name}")
            return
        except Exception as e:
            logger.error(f"Error in disconnect for {resource_name}: {e}")
    
    elif hasattr(resource, 'shutdown'):
        try:
            # Could be async or sync
            if asyncio.iscoroutinefunction(resource.shutdown):
                await asyncio.wait_for(resource.shutdown(), timeout)
            else:
                resource.shutdown()
            logger.debug(f"Shutdown completed for {resource_name}")
            return
        except Exception as e:
            logger.error(f"Error in shutdown for {resource_name}: {e}")
    
    else:
        logger.warning(f"No cleanup method found for resource {resource_name}")

class AsyncCleanupManager:
    """
    Manager for tracking and cleaning up async resources
    """
    
    def __init__(self):
        self.resources = {}
        self.logger = get_logger(__name__ + ".AsyncCleanupManager")
    
    def register(self, name: str, resource: Any):
        """
        Register a resource for cleanup
        
        Args:
            name: Name for the resource
            resource: The resource to manage
        """
        self.resources[name] = resource
        self.logger.debug(f"Registered resource '{name}' for cleanup")
    
    def unregister(self, name: str):
        """
        Unregister a resource
        
        Args:
            name: Name of the resource to unregister
        """
        if name in self.resources:
            del self.resources[name]
            self.logger.debug(f"Unregistered resource '{name}'")
    
    async def cleanup_all(self, timeout: float = 5.0):
        """
        Clean up all registered resources
        
        Args:
            timeout: Maximum time in seconds to wait for each resource cleanup
        """
        self.logger.info(f"Cleaning up {len(self.resources)} resources")
        
        for name, resource in list(self.resources.items()):
            try:
                self.logger.debug(f"Cleaning up resource '{name}'")
                await cleanup_resource(resource, timeout)
                self.unregister(name)
            except Exception as e:
                self.logger.error(f"Error cleaning up resource '{name}': {e}")
        
        self.logger.info("Cleanup completed")
