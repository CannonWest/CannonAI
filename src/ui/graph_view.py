# src/ui/graph_view.py

from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QPointF, QRectF

class ConversationGraphView(QGraphicsView):
    def __init__(self, conversation=None, parent=None):
        super().__init__(parent)

        self.conversation = conversation  # This might be a DBConversationTree object
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # Some sensible defaults:
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)  # optional: pan by dragging
        self.setInteractive(True)  # optional: for item interaction

        self.scale_factor = 1.0  # track current zoom

        # Build the initial graph if a conversation is set
        if self.conversation:
            self.refresh_graph()

    def set_conversation(self, conversation):
        """Change which conversation (DBConversationTree) is displayed, then re-draw."""
        self.conversation = conversation
        self.refresh_graph()

    def refresh_graph(self):
        """Clear and rebuild the scene based on the conversation tree data."""
        self._scene.clear()
        if not self.conversation:
            return
        root_node = self.conversation.root
        # Add layout logic to place each node. We'll define a separate method:
        self._layout_subtree(root_node, x=0, y=0, level=0)

    def _layout_subtree(self, node, x, y, level):
        """
        Recursively place this node and its children in the scene.
        'level' or 'depth' can help offset children further horizontally/vertically.
        """

        # Example: create a rect for this node
        node_width, node_height = 200, 80
        rect_item = self._scene.addRect(x, y, node_width, node_height,
                                        QPen(Qt.GlobalColor.black),
                                        QBrush(Qt.GlobalColor.white))

        # Add text label with partial content or role
        label_text = f"{node.role}\n{node.content[:50]}..."
        text_item = self._scene.addText(label_text)
        text_item.setPos(x+10, y+10)

        # Draw lines to each child
        child_spacing = 120  # vertical spacing for each child
        next_child_y = y
        for child in node.children:
            # We'll place the child to the right, for example:
            child_x = x + 300
            child_y = next_child_y
            next_child_y += (child_spacing)

            # Recursively layout child
            child_rect = self._layout_subtree(child, child_x, child_y, level+1)

            # Connect the center of the parent rect to the center of the child rect
            parent_center = QPointF(x + node_width, y + node_height/2)
            child_center = QPointF(child_x, child_y + node_height/2)
            self._scene.addLine(parent_center.x(), parent_center.y(),
                                child_center.x(), child_center.y(),
                                QPen(QColor("gray"), 2))

        # Return the rectangle area, in case parent needs it
        return QRectF(x, y, node_width, node_height)

    #
    # --------------------- ZOOM & NAVIGATION -----------------------
    #

    def wheelEvent(self, event):
        """Override wheelEvent to implement zoom on Ctrl+wheel or something similar."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.001 ** angle
            self.scale(factor, factor)
            self.scale_factor *= factor
        else:
            super().wheelEvent(event)
