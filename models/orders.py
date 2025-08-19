from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, JSON, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    shopify_id = Column(String, unique=True, index=True)
    order_number = Column(String, index=True)
    email = Column(String)
    phone = Column(String)
    
    # Customer details
    customer_name = Column(String)
    shipping_name = Column(String)
    shipping_address1 = Column(String)
    shipping_address2 = Column(String)
    shipping_city = Column(String)
    shipping_state = Column(String)
    shipping_pincode = Column(String)
    shipping_country = Column(String)
    
    # Order details
    currency = Column(String, default="INR")
    total_price = Column(Float)
    subtotal_price = Column(Float)
    total_tax = Column(Float)
    total_shipping = Column(Float)
    total_discounts = Column(Float)
    
    # Payment & Fulfillment
    payment_method = Column(String)  # cod/prepaid
    payment_status = Column(String)  # pending/paid/refunded
    fulfillment_status = Column(String)  # unfulfilled/partial/fulfilled
    current_status = Column(String, index=True)  # Computed internal status
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cancelled_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    
    # SLA tracking
    sla_due_at = Column(DateTime, nullable=True)
    sla_breached = Column(Boolean, default=False)
    
    # Metadata
    tags = Column(JSON, default=list)
    note = Column(Text)
    customization_fields = Column(JSON, default=dict)
    
    # Relationships
    line_items = relationship("OrderLineItem", back_populates="order")
    fulfillments = relationship("OrderFulfillment", back_populates="order")
    events = relationship("OrderEvent", back_populates="order")

class OrderLineItem(Base):
    __tablename__ = "order_line_items"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    shopify_id = Column(String)
    
    product_id = Column(String)
    variant_id = Column(String)
    sku = Column(String)
    title = Column(String)
    variant_title = Column(String)
    quantity = Column(Integer)
    price = Column(Float)
    
    customization_fields = Column(JSON, default=dict)
    requires_engraving = Column(Boolean, default=False)
    engraving_text = Column(String, nullable=True)
    
    order = relationship("Order", back_populates="line_items")

class OrderFulfillment(Base):
    __tablename__ = "order_fulfillments"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    shopify_id = Column(String)
    
    status = Column(String)  # pending/success/cancelled
    tracking_number = Column(String)
    tracking_url = Column(String)
    tracking_company = Column(String)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    order = relationship("Order", back_populates="fulfillments")

class OrderEvent(Base):
    __tablename__ = "order_events"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    
    event_type = Column(String)  # status_change, note_added, tag_added, etc.
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    
    actor_id = Column(String)  # User ID who made the change
    actor_name = Column(String)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    order = relationship("Order", back_populates="events")
