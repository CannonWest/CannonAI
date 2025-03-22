# src/ui/graph_view.py

from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
import time


class NodeItem(QGraphicsRectItem):
    """Custom graphics item representing a conversation node"""

    def __init__(self, node_id, role, content, x, y, width, height):
        super().__init__(x, y, width, height)
        self.node_id = node_id
        self.role = role
        self.content = content
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # Color configuration with better contrast
        role_colors = {
            "system": {
                "background": QColor("#FFB86C"),  # Orange
                "text": QColor("#2A2A2A"),  # Dark gray
                "border": QColor("#E67E22")  # Darker orange
            },
            "user": {
                "background": QColor("#50FA7B"),  # Green
                "text": QColor("#1A1A1A"),  # Near-black
                "border": QColor("#2ECC71")  # Darker green
            },
            "assistant": {
                "background": QColor("#8BE9FD"),  # Blue
                "text": QColor("#2B2B2B"),  # Dark gray
                "border": QColor("#3498DB")  # Darker blue
            }
        }

        # Fallback to neutral colors for unknown roles
        style = role_colors.get(role, {
            "background": QColor("#F0F0F0"),
            "text": QColor("#333333"),
            "border": QColor("#CCCCCC")
        })

        # Apply styles
        self.setBrush(QBrush(style["background"]))
        self.setPen(QPen(style["border"], 2))

        # Configure text appearance (you'll need to implement this in your paint method)
        self.text_color = style["text"]

        # Enhanced tooltip with HTML formatting
        tooltip_html = f"""
        <b style='color:{style["border"].name()}; font-size:12px'>{role.upper()}</b>
        <p style='color:{style["text"].name()}; margin-top:4px;'>{content}</p>
        """
        self.setToolTip(tooltip_html)


class ConversationGraphView(QGraphicsView):
    # Add signal for node selection
    node_selected = pyqtSignal(str)

    def __init__(self, conversation=None, parent=None):
        super().__init__(parent)

        self.conversation = conversation  # This might be a DBConversationTree object
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # Track node items by ID for easier access
        self.node_items = {}
        self.current_branch_ids = set()

        # Some sensible defaults:
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)  # optional: pan by dragging
        self.setInteractive(True)  # optional: for item interaction

        self.scale_factor = 1.0  # track current zoom
        self._last_update_time = 0  # Add this line to track the last update time

        # Enable scene mouse events
        self._scene.mouseReleaseEvent = self._handle_scene_mouse_release

        self._update_in_progress = False
        self._layout_in_progress = False

        # Build the initial graph if a conversation is set
        if self.conversation:
            self.update_tree(self.conversation)

    def _handle_scene_mouse_release(self, event):
        """Handle mouse release events on the scene to detect node clicks"""
        items = self._scene.items(event.scenePos())
        for item in items:
            if isinstance(item, NodeItem):
                self.node_selected.emit(item.node_id)
                break
        # Call original implementation
        QGraphicsScene.mouseReleaseEvent(self._scene, event)

    def set_conversation(self, conversation):
        """Change which conversation (DBConversationTree) is displayed, then re-draw."""
        self.conversation = conversation
        self.update_tree(self.conversation)

    def update_tree(self, conversation_tree):
        """Clear and rebuild the scene based on the conversation tree data"""
        # Skip update if we're marked as busy to prevent layout thrashing
        current_time = time.time()
        if hasattr(self, '_update_in_progress') and self._update_in_progress:
            # If it's been more than 2 seconds since the last update, force an update
            if current_time - self._last_update_time > 2:
                self._update_in_progress = False
            else:
                return
            return

        # Skip if we're in the middle of a layout operation
        if hasattr(self, '_layout_in_progress') and self._layout_in_progress:
            return

        self._last_update_time = current_time  # Update the last update time

        try:
            self._update_in_progress = True

            self._scene.clear()
            self.node_items = {}

            if not conversation_tree:
                return

            # Safety check - avoid processing extremely large trees
            try:
                # Get the current branch for highlighting
                current_branch = conversation_tree.get_current_branch()
                if not current_branch:
                    print("Warning: Empty branch returned from get_current_branch()")
                    return

                self.current_branch_ids = {node.id for node in current_branch if node is not None}

                # Start layout from the root node
                root_node = conversation_tree.root
                if not root_node:
                    print("Warning: No root node in conversation tree")
                    return

                # Set a layout in progress flag to prevent recursion
                self._layout_in_progress = True
                self._layout_subtree(root_node, x=0, y=0, level=0)
                self._layout_in_progress = False

                # Use try/except for view operations that might fail
                try:
                    # Fit the view to show all content
                    self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

                    # Set a reasonable scene rect with some padding
                    sceneRect = self._scene.itemsBoundingRect()
                    sceneRect.adjust(-100, -100, 100, 100)  # Add some padding
                    self._scene.setSceneRect(sceneRect)
                except Exception as view_error:
                    print(f"Error updating graph view layout: {str(view_error)}")
            except Exception as branch_error:
                print(f"Error getting conversation branch: {str(branch_error)}")

        except Exception as e:
            print(f"Critical error in graph view update: {str(e)}")
        finally:
            self._update_in_progress = False
            self._layout_in_progress = False

    def _layout_subtree(self, node, x, y, level, max_depth=0):
        """
        Recursively place this node and its children in the scene.
        'level' or 'depth' can help offset children further horizontally/vertically.
        max_depth limits recursion to prevent stack overflow.
        """
        if max_depth != 0:
            # Safety check - prevent excessive recursion
            if level > max_depth:
                return QRectF(x, y, 200, 80)

            # Safety check - ensure node is valid
            if not node:
                return QRectF(x, y, 200, 80)
        # Skip root system message node
        if node.role == "system" and node.parent_id is not None:
            return  # Just return, don't create NodeItem or recurse children

        try:
            # Dimensions and styling
            node_width, node_height = 200, 80

            # Create a node item
            node_item = NodeItem(
                node_id=node.id,
                role=node.role,
                content=node.content,
                x=x, y=y,
                width=node_width,
                height=node_height
            )

            # Highlight if node is in current branch
            if node.id in self.current_branch_ids:
                node_item.setPen(QPen(QColor("gold"), 3))

            # Add the node to the scene
            self._scene.addItem(node_item)

            # Store reference to the node item
            self.node_items[node.id] = node_item

            from src.utils.file_utils import extract_display_text

            # Add text label with our extracted display text
            display_text = extract_display_text(node, max_length=40)
            label_text = f"{node.role}:\n{display_text}"

            text_item = QGraphicsTextItem(label_text)
            text_item.setPos(x + 5, y + 5)
            text_item.setTextWidth(node_width - 10)
            self._scene.addItem(text_item)

            # Calculate child positions and draw connections
            children = getattr(node, 'children', [])
            if children and len(children) > 0:
                # Limit to maximum 10 children to prevent excessive branching
                if len(children) > 10:
                    children = children[:10]

                # Determine total width needed for children
                child_spacing = 220  # horizontal spacing between siblings
                total_width = (len(children) - 1) * child_spacing

                # Start position for first child
                first_child_x = x - (total_width / 2)
                child_y = y + 150  # Place children below parent

                for i, child in enumerate(children):
                    # Skip None children
                    if not child:
                        continue

                    # Place child below and appropriately spaced horizontally
                    child_x = first_child_x + (i * child_spacing)

                    # Recursively layout the child with incremented depth
                    self._layout_subtree(child, child_x, child_y, level + 1, max_depth)

                    # Draw a connecting line from parent to child
                    parent_center = QPointF(x + node_width / 2, y + node_height)
                    child_center = QPointF(child_x + node_width / 2, child_y)

                    # Use a different color for current branch connections
                    line_color = QColor("gold") if (node.id in self.current_branch_ids and
                                                    child.id in self.current_branch_ids) else QColor("gray")

                    line = self._scene.addLine(
                        parent_center.x(), parent_center.y(),
                        child_center.x(), child_center.y(),
                        QPen(line_color, 2)
                    )
                    line.setZValue(-1)  # Put lines behind nodes

            # Return the rectangle area, in case parent needs it
            return QRectF(x, y, node_width, node_height)
        except Exception as e:
            print(f"Error in _layout_subtree: {str(e)}")
            return QRectF(x, y, 200, 80)

    #
    # --------------------- ZOOM & NAVIGATION -----------------------
    #

    def wheelEvent(self, event):
        """Override wheelEvent to implement zoom on Ctrl+wheel"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.1 if angle > 0 else 0.9
            self.scale(factor, factor)
            self.scale_factor *= factor
        else:
            super().wheelEvent(event)
