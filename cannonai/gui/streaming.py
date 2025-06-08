#!/usr/bin/env python3
"""
CannonAI GUI Streaming Module - Handles Server-Sent Events (SSE) generation and streaming logic

This module provides utilities for streaming AI responses via Server-Sent Events,
managing the async producer/consumer pattern between the AI client and Flask's response stream.
"""

import json
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from gui.api_handlers import APIHandlers

logger = logging.getLogger("cannonai.gui.streaming")


class StreamingError(Exception):
    """Custom exception for streaming-related errors."""
    pass


def format_sse_message(data: Dict[str, Any]) -> str:
    """
    Formats a data dictionary as a Server-Sent Events message.
    
    Args:
        data: The data to send to the client
        
    Returns:
        SSE-formatted string with 'data:' prefix and double newline
    """
    print(f"[Streaming] Formatting SSE message with keys: {list(data.keys())}")
    return f"data: {json.dumps(data)}\n\n"


def create_error_stream(error_message: str) -> AsyncGenerator[str, None]:
    """
    Creates a simple async generator that yields a single error message.
    
    Args:
        error_message: The error message to send
        
    Yields:
        SSE-formatted error message
    """
    async def error_generator():
        print(f"[Streaming] Creating error stream with message: {error_message}")
        yield format_sse_message({'error': error_message})
    
    return error_generator()


async def stream_with_queue(
    api_handlers: 'APIHandlers',
    message_content: str,
    event_loop: asyncio.AbstractEventLoop,
    timeout_seconds: int = 90
) -> AsyncGenerator[str, None]:
    """
    Main streaming function that manages the async producer/consumer pattern.
    
    This function creates a queue to bridge between the async AI response generator
    and Flask's synchronous response stream. It handles timeouts, errors, and
    proper cleanup.
    
    Args:
        api_handlers: The APIHandlers instance with stream_message method
        message_content: The user's message content
        event_loop: The GUI event loop where async operations run
        timeout_seconds: Timeout for queue operations
        
    Yields:
        SSE-formatted messages for the client
    """
    print(f"[Streaming] Starting stream_with_queue for message: '{message_content[:50]}...'")
    queue: asyncio.Queue[Optional[Dict[Any, Any]]] = asyncio.Queue()
    producer_task: Optional[asyncio.Task] = None
    
    async def producer():
        """Producer coroutine that gets AI responses and puts them in the queue."""
        try:
            print(f"[Streaming] Producer starting for message: '{message_content[:50]}...'")
            async for item in api_handlers.stream_message(message_content):
                print(f"[Streaming] Producer received item with keys: {list(item.keys()) if isinstance(item, dict) else 'non-dict'}")
                await queue.put(item)
                
                # Check for completion or error conditions
                if isinstance(item, dict) and (item.get("done") or item.get("error")):
                    print(f"[Streaming] Producer detected end condition: done={item.get('done')}, error={item.get('error')}")
                    break
                    
        except Exception as e:
            error_msg = f"Streaming producer error: {str(e)}"
            print(f"[Streaming] Producer error: {error_msg}")
            logger.error(error_msg, exc_info=True)
            await queue.put({"error": error_msg})
        finally:
            print("[Streaming] Producer finished, sending sentinel")
            await queue.put(None)  # Sentinel to indicate end of stream
    
    try:
        # Schedule the producer on the GUI event loop
        if event_loop and event_loop.is_running():
            print("[Streaming] Scheduling producer on GUI event loop")
            producer_task = asyncio.run_coroutine_threadsafe(producer(), event_loop)
        else:
            error_msg = "Server event loop not available for streaming"
            print(f"[Streaming] Error: {error_msg}")
            logger.error(error_msg)
            yield format_sse_message({'error': error_msg})
            return
        
        # Consumer loop - runs in Flask's context
        items_processed = 0
        start_time = datetime.now()
        
        while True:
            try:
                print(f"[Streaming] Consumer waiting for item (processed: {items_processed})")
                
                # Check if event loop is still running
                if not event_loop or not event_loop.is_running():
                    error_msg = "Stream interrupted: server event loop stopped"
                    print(f"[Streaming] Error: {error_msg}")
                    logger.warning(error_msg)
                    yield format_sse_message({'error': error_msg})
                    break
                
                # Get item from queue with timeout
                item_future = asyncio.run_coroutine_threadsafe(queue.get(), event_loop)
                item = item_future.result(timeout=timeout_seconds)
                
                if item is None:  # Sentinel received
                    print(f"[Streaming] Consumer received sentinel after {items_processed} items")
                    logger.debug(f"SSE stream complete after {items_processed} items")
                    break
                
                items_processed += 1
                print(f"[Streaming] Consumer yielding item #{items_processed}")
                yield format_sse_message(item)
                
                # Check for completion conditions
                if item.get("error") or item.get("done"):
                    elapsed = (datetime.now() - start_time).total_seconds()
                    print(f"[Streaming] Stream ended by event after {elapsed:.2f}s: {item}")
                    logger.info(f"SSE stream ended after {elapsed:.2f}s and {items_processed} items")
                    break
                    
            except asyncio.TimeoutError:
                error_msg = f"Stream timeout after {timeout_seconds}s waiting for response"
                print(f"[Streaming] Timeout error: {error_msg}")
                logger.warning(error_msg)
                yield format_sse_message({'error': error_msg})
                break
                
            except Exception as e:
                error_msg = f"Streaming consumer error: {str(e)}"
                print(f"[Streaming] Consumer error: {error_msg}")
                logger.error(error_msg, exc_info=True)
                yield format_sse_message({'error': error_msg})
                break
                
    finally:
        # Cleanup
        print("[Streaming] Cleaning up stream resources")
        if producer_task and not producer_task.done():
            print("[Streaming] Cancelling producer task")
            producer_task.cancel()
            
        elapsed_total = (datetime.now() - start_time).total_seconds()
        print(f"[Streaming] Stream completed after {elapsed_total:.2f}s total")
        logger.info(f"Stream cleanup complete after {elapsed_total:.2f}s")


async def test_streaming_connection(event_loop: asyncio.AbstractEventLoop) -> AsyncGenerator[str, None]:
    """
    Test function to verify SSE streaming is working.
    
    Args:
        event_loop: The GUI event loop
        
    Yields:
        Test SSE messages
    """
    print("[Streaming] Running streaming connection test")
    
    async def test_producer(queue: asyncio.Queue):
        """Simple test producer that sends a few messages."""
        messages = [
            {"type": "info", "message": "Streaming test started"},
            {"type": "progress", "message": "Processing...", "percent": 50},
            {"type": "info", "message": "Test complete"},
            {"done": True, "message": "Streaming test successful"}
        ]
        
        for i, msg in enumerate(messages):
            print(f"[Streaming] Test producer sending message {i+1}/{len(messages)}")
            await queue.put(msg)
            await asyncio.sleep(0.5)  # Simulate processing time
            
        await queue.put(None)  # Sentinel
    
    queue: asyncio.Queue = asyncio.Queue()
    
    # Schedule test producer
    if event_loop and event_loop.is_running():
        asyncio.run_coroutine_threadsafe(test_producer(queue), event_loop)
    else:
        yield format_sse_message({'error': 'Test failed: no event loop'})
        return
    
    # Consume test messages
    while True:
        try:
            item_future = asyncio.run_coroutine_threadsafe(queue.get(), event_loop)
            item = item_future.result(timeout=5)
            
            if item is None:
                break
                
            yield format_sse_message(item)
            
            if item.get("done"):
                break
                
        except asyncio.TimeoutError:
            yield format_sse_message({'error': 'Test timeout'})
            break
        except Exception as e:
            yield format_sse_message({'error': f'Test error: {str(e)}'})
            break
    
    print("[Streaming] Test streaming completed")
