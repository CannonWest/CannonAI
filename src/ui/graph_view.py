# src/ui/graph_view.py

from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal


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

        # Enable scene mouse events
        self._scene.mouseReleaseEvent = self._handle_scene_mouse_release

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
        """Clear and rebuild the scene based on the conversation tree data (mimics ConversationTreeWidget API)"""
        self._scene.clear()
        self.node_items = {}

        if not conversation_tree:
            return

        # Get the current branch for highlighting
        current_branch = conversation_tree.get_current_branch()
        self.current_branch_ids = {node.id for node in current_branch}

        # Start layout from the root node
        root_node = conversation_tree.root
        self._layout_subtree(root_node, x=0, y=0, level=0)

        # Fit the view to show all content
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        # Set a reasonable scene rect with some padding
        sceneRect = self._scene.itemsBoundingRect()
        sceneRect.adjust(-100, -100, 100, 100)  # Add some padding
        self._scene.setSceneRect(sceneRect)

    def _layout_subtree(self, node, x, y, level):
        """
        Recursively place this node and its children in the scene.
        'level' or 'depth' can help offset children further horizontally/vertically.
        """
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

        # Add text label with partial content
        preview = node.content
        if len(preview) > 40:
            preview = preview[:37] + "..."

        label_text = f"{node.role}:\n{preview}"
        text_item = QGraphicsTextItem(label_text)
        text_item.setPos(x + 5, y + 5)
        text_item.setTextWidth(node_width - 10)
        self._scene.addItem(text_item)

        # Calculate child positions and draw connections
        if node.children:
            # Determine total height needed for children
            child_spacing = 120  # vertical spacing between siblings
            total_height = (len(node.children) - 1) * child_spacing

            # Start position for first child
            first_child_y = y - (total_height / 2)

            for i, child in enumerate(node.children):
                # Place child to the right and appropriately spaced vertically
                child_x = x + 300  # horizontal spacing
                child_y = first_child_y + (i * child_spacing)

                # Recursively layout the child
                self._layout_subtree(child, child_x, child_y, level + 1)

                # Draw a connecting line from parent to child
                parent_center = QPointF(x + node_width, y + node_height / 2)
                child_center = QPointF(child_x, child_y + node_height / 2)

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